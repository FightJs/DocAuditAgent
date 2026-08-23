"""LangGraph StateGraph assembly for the audit workflow.

Main chain (HITL spec section 4):

    prepare_run -> agent_review -> triage
        -> [no human required] finalize (ready_for_delivery)
        -> [human required] human_review (interrupt) -> route by decision
            -> transfer/escalate -> human_review (re-pause for new owner)
            -> approve/reject/request_supplement -> finalize

Checkpointing: pass a durable checkpointer (e.g. Postgres/Redis saver) in
production; the InMemorySaver default exists only for MVP dev and tests.
The `thread_id` is always the `audit_run_id` - the HITL boundary is one
document version + one fixed baseline + one audit run.
"""

from __future__ import annotations

from typing import Any, Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.workflow.llm import AgentReviewer
from app.workflow.nodes import (
    NODE_AGENT_REVIEW,
    NODE_FINALIZE,
    NODE_HUMAN_REVIEW,
    NODE_PREPARE,
    NODE_TRIAGE,
    finalize_node,
    human_review_node,
    make_agent_review_node,
    prepare_run_node,
    route_after_agent_review,
    route_after_human,
    route_after_prepare,
    route_after_triage,
    triage_node,
)
from app.workflow.state import AuditRunState


def build_audit_workflow(
    reviewer: AgentReviewer,
    *,
    checkpointer: Optional[Any] = None,
):
    """Compile the audit workflow graph around the given agent reviewer."""
    graph = StateGraph(AuditRunState)
    graph.add_node(NODE_PREPARE, prepare_run_node)
    graph.add_node(NODE_AGENT_REVIEW, make_agent_review_node(reviewer))
    graph.add_node(NODE_TRIAGE, triage_node)
    graph.add_node(NODE_HUMAN_REVIEW, human_review_node)
    graph.add_node(NODE_FINALIZE, finalize_node)

    graph.add_edge(START, NODE_PREPARE)
    graph.add_conditional_edges(
        NODE_PREPARE,
        route_after_prepare,
        {NODE_AGENT_REVIEW: NODE_AGENT_REVIEW, "end": END},
    )
    graph.add_conditional_edges(
        NODE_AGENT_REVIEW,
        route_after_agent_review,
        {NODE_TRIAGE: NODE_TRIAGE, "end": END},
    )
    graph.add_conditional_edges(
        NODE_TRIAGE,
        route_after_triage,
        {NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW, NODE_FINALIZE: NODE_FINALIZE},
    )
    graph.add_conditional_edges(
        NODE_HUMAN_REVIEW,
        route_after_human,
        {NODE_HUMAN_REVIEW: NODE_HUMAN_REVIEW, NODE_FINALIZE: NODE_FINALIZE},
    )
    graph.add_edge(NODE_FINALIZE, END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
