"""受控恢复与版本失效：覆盖 hitl arch 6.2/6.3 与 api_spec 6.4。"""

import json
import unittest

from tests.unit.hitl import helpers  # noqa: F401 触发 sys.path 引导
from tests.unit.hitl.helpers import (
    CONTEXT,
    REVIEWER,
    THREAD_ID,
    make_service,
    open_and_accept,
)
from tests.unit.hitl.test_decisions import edit_kwargs

from app.hitl import (
    AssignmentStatus,
    AuditEventType,
    InterruptStatus,
    StaleHumanTaskError,
)


class ResumeTest(unittest.TestCase):
    def test_resume_uses_same_thread_id_after_persistence(self):
        """恢复必须使用同一 thread_id，且发生在决定落库与审计之后。"""
        service, _, adapter = make_service()
        assignment = open_and_accept(service)
        outcome = service.submit_decision(**edit_kwargs(assignment))

        self.assertEqual(len(adapter.calls), 1)
        thread_id, command = adapter.calls[0]
        self.assertEqual(thread_id, THREAD_ID)
        self.assertEqual(command.interrupt_id, outcome.resumed_interrupt.interrupt_id)
        self.assertEqual(command.decision_id, outcome.decision.decision_id)
        self.assertEqual(command.value["action"], "edit")
        json.dumps(command.value, ensure_ascii=False)  # 恢复值 JSON 可序列化

        resume_events = [
            e for e in service.store.audit_events
            if e.event_type is AuditEventType.INTERRUPT_RESUMED
        ]
        self.assertEqual(len(resume_events), 1)
        self.assertEqual(resume_events[0].actor_id, REVIEWER[0])

    def test_resumed_interrupt_not_resumed_twice(self):
        """已恢复的中断不会因后续决定重复恢复。"""
        service, _, adapter = make_service()
        assignment = open_and_accept(service)
        service.submit_decision(**edit_kwargs(assignment, key="dec-1"))
        service.submit_decision(**edit_kwargs(assignment, key="dec-2"))
        self.assertEqual(len(adapter.calls), 1)

    def test_invalidate_run_blocks_resume_and_keeps_history(self):
        """版本/基线变化：旧中断失效、旧待办替代、历史只读保留。"""
        service, _, _ = make_service()
        assignment = open_and_accept(service)
        interrupt_id = assignment.interrupt_id

        service.invalidate_run(audit_run_id=CONTEXT.audit_run_id, reason="新版本已创建")

        interrupt = service.store.get_interrupt(interrupt_id)
        self.assertEqual(interrupt.status, InterruptStatus.INVALIDATED)
        self.assertEqual(assignment.status, AssignmentStatus.SUPERSEDED)
        # 历史记录未被删除
        self.assertIn(interrupt_id, service.store.interrupts)
        self.assertIn(assignment.assignment_id, service.store.assignments)

        with self.assertRaises(StaleHumanTaskError):
            service.submit_decision(**edit_kwargs(assignment))


if __name__ == "__main__":
    unittest.main()
