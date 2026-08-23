"""图执行恢复适配层（LangGraph 接缝）。

约束来源：
- api_spec 6.4：前端不得直接调用 Command(resume=...)/checkpoint/thread_id；
  后端在决定成功落库、生成审计事件、更新投影之后，才按当前有效上下文恢复图执行。
- hitl arch 6.2：恢复必须使用同一 thread_id，恢复值必须结构化、JSON 可序列化
  且已通过业务校验。
- 团队 plan：LangChain MCP 当前不可用，具体 SDK 依赖与调用集中在适配层，
  测试使用离线 stub。

本文件不 import langgraph；真实实现（LangGraphResumeAdapter）在 SDK 版本经
官方文档复核后补充，只需满足 GraphResumeAdapter 协议。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import InvalidActionPayloadError


def ensure_json_serializable(value: Any, *, what: str) -> None:
    """中断 payload 与恢复值必须 JSON 可序列化、最小化（hitl arch 5/7）。"""

    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise InvalidActionPayloadError(f"{what} 必须 JSON 可序列化: {exc}") from exc


@dataclass(frozen=True)
class ResumeCommand:
    """发送给图执行的恢复命令（等价 LangGraph Command(resume=...) 的业务载体）。"""

    interrupt_id: str
    decision_id: str
    action: str
    value: dict[str, Any]  # 已业务校验、JSON 可序列化的恢复值


class GraphResumeAdapter(Protocol):
    """图执行恢复适配协议。实现方负责 thread_id → 图执行的受控恢复。"""

    def resume(self, thread_id: str, command: ResumeCommand) -> None:
        ...


@dataclass
class StubGraphAdapter:
    """离线 stub：记录恢复调用，供单元测试与无 SDK 环境使用。"""

    calls: list[tuple[str, ResumeCommand]] = field(default_factory=list)

    def resume(self, thread_id: str, command: ResumeCommand) -> None:
        ensure_json_serializable(command.value, what="恢复值")
        self.calls.append((thread_id, command))
