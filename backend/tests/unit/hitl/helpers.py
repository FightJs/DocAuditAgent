"""HITL 单元测试公共夹具。"""

from tests.unit.hitl._bootstrap import BACKEND_ROOT as _  # noqa: F401 确保 sys.path 就绪

from app.hitl import (
    ActorRole,
    ContextTriple,
    HitlService,
    InterruptPoint,
    RoutingReason,
    StaticContextValidator,
    StubGraphAdapter,
)

CONTEXT = ContextTriple(
    case_id="case_1",
    document_version_id="docv_1",
    audit_run_id="run_1",
    baseline_version_id="baseline_2026_01",
)
THREAD_ID = "thread_run_1"
REVIEWER = ("user_reviewer", ActorRole.REVIEWER)
APPROVER = ("user_approver", ActorRole.APPROVER)


def make_service() -> tuple[HitlService, StaticContextValidator, StubGraphAdapter]:
    validator = StaticContextValidator()
    adapter = StubGraphAdapter()
    service = HitlService(context_validator=validator, graph_adapter=adapter)
    return service, validator, adapter


def open_default_interrupt(service: HitlService):
    return service.open_interrupt(
        point=InterruptPoint.RISK_ITEM_REVIEW,
        thread_id=THREAD_ID,
        context=CONTEXT,
        routing_reasons=[RoutingReason.HIGH_SEVERITY],
        queue_code="legal_review",
        payload={"summary": "1 条高严重度风险待复核", "risk_item_ids": ["finding_1"]},
    )


def open_and_accept(service: HitlService, actor=REVIEWER):
    _, assignment, _ = open_default_interrupt(service)
    service.accept_assignment(
        assignment_id=assignment.assignment_id,
        actor_id=actor[0],
        actor_role=actor[1],
        expected_revision=assignment.revision,
        idempotency_key="accept-1",
    )
    return assignment
