"""中断开启与待办去重：覆盖 hitl arch 第 5/7 节约束。"""

import unittest

from tests.unit.hitl import helpers  # noqa: F401 触发 sys.path 引导
from tests.unit.hitl.helpers import CONTEXT, THREAD_ID, make_service, open_default_interrupt

from app.hitl import (
    ActionNotAllowedError,
    AssignmentStatus,
    AuditEventType,
    InterruptPoint,
    InterruptStatus,
    InvalidActionPayloadError,
    RoutingReason,
)


class OpenInterruptTest(unittest.TestCase):
    def test_open_creates_interrupt_assignment_and_audit(self):
        service, _, _ = make_service()
        interrupt, assignment, created = open_default_interrupt(service)

        self.assertTrue(created)
        self.assertEqual(interrupt.status, InterruptStatus.PENDING)
        self.assertEqual(interrupt.thread_id, THREAD_ID)
        self.assertEqual(interrupt.context, CONTEXT)
        self.assertEqual(assignment.status, AssignmentStatus.QUEUED)
        self.assertEqual(assignment.interrupt_id, interrupt.interrupt_id)
        self.assertEqual(assignment.routing_reasons, [RoutingReason.HIGH_SEVERITY])

        events = service.store.audit_events
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, AuditEventType.INTERRUPT_OPENED)
        self.assertEqual(events[0].context, CONTEXT)

    def test_reexecution_after_resume_does_not_duplicate_assignment(self):
        """恢复后中断节点从开头重执行：同 thread_id + point 必须幂等去重。"""
        service, _, _ = make_service()
        first_interrupt, first_assignment, created1 = open_default_interrupt(service)
        second_interrupt, second_assignment, created2 = open_default_interrupt(service)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first_interrupt.interrupt_id, second_interrupt.interrupt_id)
        self.assertEqual(first_assignment.assignment_id, second_assignment.assignment_id)
        self.assertEqual(len(service.store.assignments), 1)
        self.assertEqual(len(service.store.interrupts), 1)
        self.assertEqual(len(service.store.audit_events), 1)  # 不重复写审计

    def test_second_active_assignment_for_same_run_rejected(self):
        """同一审核运行任一时刻最多一条活跃待办（数据模型 1.1 约束）。"""
        service, _, _ = make_service()
        open_default_interrupt(service)

        with self.assertRaises(ActionNotAllowedError):
            service.open_interrupt(
                point=InterruptPoint.RISK_TRIAGE,
                thread_id=THREAD_ID,
                context=CONTEXT,
                routing_reasons=[RoutingReason.REDLINE],
                queue_code="legal_review",
                payload={"summary": "另一中断点"},
            )

    def test_payload_must_be_json_serializable(self):
        service, _, _ = make_service()
        with self.assertRaises(InvalidActionPayloadError):
            service.open_interrupt(
                point=InterruptPoint.RISK_TRIAGE,
                thread_id=THREAD_ID,
                context=CONTEXT,
                routing_reasons=[RoutingReason.REDLINE],
                queue_code="legal_review",
                payload={"bad": object()},
            )


if __name__ == "__main__":
    unittest.main()
