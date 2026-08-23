"""Audit workflow module (Teammate 1 scope of the backend MVP plan).

LangGraph HITL orchestration for one audit run (document version + fixed
baseline). Public surface:

- `build_audit_workflow(reviewer, checkpointer=...)` - compile the graph.
- `AuditWorkflowRunner` - start / resume / snapshot integration API.
- `AgentReviewer` protocol + `LLMAgentReviewer` + `build_chat_model` - the
  adapter layer concentrating LangChain SDK usage (offline stubs in tests).
- `WorkflowLLMSettings` - DEEPSEEK_* environment configuration.

The module never writes business case status, never persists human decisions
and never auto-approves; those belong to backend services.
"""

from app.workflow import constants
from app.workflow.graph import build_audit_workflow
from app.workflow.llm import (
    AgentReviewer,
    AgentReviewError,
    LLMAgentReviewer,
    WorkflowConfigError,
    build_chat_model,
)
from app.workflow.runner import (
    AuditWorkflowRunner,
    RunNotFoundError,
    RunNotPausedError,
    RunSnapshot,
    ThreadMismatchError,
)
from app.workflow.settings import WorkflowLLMSettings
from app.workflow.state import (
    AuditRunInput,
    AuditRunState,
    CandidateFinding,
    HumanDecisionInput,
    InvalidResumePayload,
    ReviewRequest,
)

__all__ = [
    "AgentReviewer",
    "AgentReviewError",
    "AuditRunInput",
    "AuditRunState",
    "AuditWorkflowRunner",
    "CandidateFinding",
    "HumanDecisionInput",
    "InvalidResumePayload",
    "LLMAgentReviewer",
    "ReviewRequest",
    "RunNotFoundError",
    "RunNotPausedError",
    "RunSnapshot",
    "ThreadMismatchError",
    "WorkflowConfigError",
    "WorkflowLLMSettings",
    "build_audit_workflow",
    "build_chat_model",
    "constants",
]
