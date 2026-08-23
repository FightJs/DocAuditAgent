"""Runner API wrapping the compiled audit workflow graph.

This is the integration surface for backend services (Teammate 3) and e2e
tests (Teammate 4). Responsibilities here:

- `thread_id` is always the `audit_run_id`; starting a run binds the two.
- Resume payloads are validated BEFORE touching the graph. LangGraph
  consumes a resume value even when the resumed node later fails, so invalid
  values must never reach `Command(resume=...)`.
- An optional `resume_guard` hook lets services enforce the HITL spec's
  pre-resume checks (authorization, responsibility, version/run validity,
  supersession) without the workflow module owning those rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from langgraph.types import Command

from app.workflow.graph import build_audit_workflow
from app.workflow.llm import AgentReviewer
from app.workflow.state import (
    AuditRunInput,
    HumanDecisionInput,
    validate_resume_payload,
)


class RunNotFoundError(KeyError):
    """No checkpointed state exists for the given thread/audit_run_id."""


class RunNotPausedError(RuntimeError):
    """The run is not paused waiting for human input (or already ended)."""


class ThreadMismatchError(ValueError):
    """thread_id must equal audit_run_id (HITL boundary per run)."""


#: Services hook: receives the run context, raises to forbid the resume.
ResumeGuard = Callable[[dict[str, Any]], None]


@dataclass
class RunSnapshot:
    """Read-model of a run's graph state for services and tests."""

    thread_id: str
    run_status: Optional[str]
    outcome: Optional[str]
    awaiting_human: bool
    interrupt_payload: Optional[dict[str, Any]]
    requires_human: bool
    routing_reasons: list[str] = field(default_factory=list)
    routing_details: list[str] = field(default_factory=list)
    human_decision_count: int = 0
    error: Optional[dict[str, Any]] = None
    values: dict[str, Any] = field(default_factory=dict)


class AuditWorkflowRunner:
    """Start, resume and inspect audit runs on the compiled graph."""

    def __init__(
        self,
        graph: Any = None,
        *,
        reviewer: Optional[AgentReviewer] = None,
        checkpointer: Optional[Any] = None,
        resume_guard: Optional[ResumeGuard] = None,
    ):
        if graph is None:
            if reviewer is None:
                raise ValueError("either graph or reviewer is required")
            graph = build_audit_workflow(reviewer, checkpointer=checkpointer)
        self._graph = graph
        self._resume_guard = resume_guard

    # -- lifecycle ----------------------------------------------------

    def start(self, run_input: AuditRunInput) -> RunSnapshot:
        """Start a run; pauses at human_review or runs to completion."""
        thread_id = run_input.get("audit_run_id", "")
        if not thread_id:
            raise ThreadMismatchError("audit_run_id is required as thread_id")
        self._graph.invoke(dict(run_input), self._config(thread_id))
        return self.snapshot(thread_id)

    def resume(self, thread_id: str, decision: dict[str, Any]) -> RunSnapshot:
        """Resume a paused run with a validated human decision payload."""
        current = self.snapshot(thread_id)
        if not current.awaiting_human:
            raise RunNotPausedError(
                f"run {thread_id!r} is not awaiting human input "
                f"(status={current.run_status!r})"
            )
        validated: HumanDecisionInput = validate_resume_payload(decision)
        if self._resume_guard is not None:
            self._resume_guard(
                {
                    "case_id": current.values.get("case_id"),
                    "document_version_id": current.values.get("document_version_id"),
                    "audit_run_id": current.values.get("audit_run_id"),
                    "baseline_version_id": current.values.get("baseline_version_id"),
                    "run_status": current.run_status,
                }
            )
        self._graph.invoke(Command(resume=dict(validated)), self._config(thread_id))
        return self.snapshot(thread_id)

    # -- introspection -------------------------------------------------

    def snapshot(self, thread_id: str) -> RunSnapshot:
        snap = self._graph.get_state(self._config(thread_id))
        values = dict(snap.values or {})
        if not values and not snap.next:
            raise RunNotFoundError(thread_id)
        payload: Optional[dict[str, Any]] = None
        for task in snap.tasks:
            if task.interrupts:
                payload = dict(task.interrupts[0].value)
                break
        return RunSnapshot(
            thread_id=thread_id,
            run_status=values.get("run_status"),
            outcome=values.get("outcome"),
            awaiting_human=bool(snap.next) and payload is not None,
            interrupt_payload=payload,
            requires_human=bool(values.get("requires_human", False)),
            routing_reasons=list(values.get("routing_reasons", [])),
            routing_details=list(values.get("routing_details", [])),
            human_decision_count=len(values.get("human_decisions", [])),
            error=values.get("error"),
            values=values,
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}
