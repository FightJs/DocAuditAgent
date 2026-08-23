"""LLM adapter layer for the audit workflow.

All LangChain SDK dependencies are concentrated here (team plan requirement:
concentrate SDK dependencies and calls in an adapter layer). Graph nodes
depend only on the `AgentReviewer` protocol, so unit tests run fully offline
with stubs and the real adapter can be rewired without touching graph code.

The real adapter uses a LangChain `ChatOpenAI`-compatible client pointed at
the DeepSeek endpoint from `WorkflowLLMSettings`. Recorded research risk: the
LangChain docs MCP was unavailable during design, so SDK signatures must be
re-verified against official docs before production use.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.workflow import constants as c
from app.workflow.settings import WorkflowLLMSettings
from app.workflow.state import CandidateFinding, ReviewRequest

PROMPT_VERSION = "mvp-v1"


class WorkflowConfigError(RuntimeError):
    """Raised when the workflow LLM adapter is misconfigured (e.g. no key)."""


class AgentReviewError(RuntimeError):
    """Raised when the agent reviewer fails or returns unusable output."""


class AgentReviewer(Protocol):
    """Produces candidate findings for one fixed version+baseline run."""

    def review(self, request: ReviewRequest) -> list[CandidateFinding]:
        ...


def build_chat_model(settings: WorkflowLLMSettings) -> Any:
    """Construct the ChatOpenAI-compatible client.

    The langchain-openai import is lazy so that importing the workflow
    package never requires the SDK (unit tests use stubs and stay offline).
    """
    if not settings.api_key:
        raise WorkflowConfigError(
            "DeepSeek API key missing; set DEEPSEEK_API_KEY in backend/.env"
        )
    from langchain_openai import ChatOpenAI  # lazy SDK import by design

    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
    )


_SYSTEM_PROMPT = (
    "你是合同文档审核助手。仅依据给定解析文本与审核基线识别候选风险项。"
    "只输出 JSON 数组, 每项包含字段: finding_ref, category, title, summary, "
    "severity(critical/high/medium/low), confidence_band(high/medium/low/unknown), "
    "is_redline(bool), hit_type(rule_hit/llm_inferred/conflict/evidence_gap), "
    "locator_ids(string[]), locator_status(ok/approximate/stale/unavailable), "
    "authority_ref_ids(string[]), limitations(string[]), "
    "rule_evaluation_status(passed/inconclusive/failed/skipped)。"
    "无候选风险时输出空数组。不要输出任何解释性文字。"
)


class LLMAgentReviewer:
    """AgentReviewer backed by a ChatOpenAI-compatible chat model."""

    def __init__(self, chat_model: Any, *, prompt_version: str = PROMPT_VERSION):
        self._chat_model = chat_model
        self.prompt_version = prompt_version

    def review(self, request: ReviewRequest) -> list[CandidateFinding]:
        from langchain_core.messages import HumanMessage, SystemMessage

        human = json.dumps(
            {
                "baseline_version_id": request["baseline_version_id"],
                "parsed_document": request["parsed_document"],
            },
            ensure_ascii=False,
        )
        try:
            response = self._chat_model.invoke(
                [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)]
            )
        except Exception as exc:  # SDK/network failure surfaces as agent_failed
            raise AgentReviewError(f"chat model invocation failed: {exc}") from exc
        return parse_findings_json(getattr(response, "content", response))


def parse_findings_json(content: Any) -> list[CandidateFinding]:
    """Parse the model's JSON array response into normalized candidates.

    Missing or unknown enum-like fields are normalized to conservative values
    ("unknown"/"failed") so that triage forces human review instead of
    silently trusting malformed model output.
    """
    if isinstance(content, list):  # langchain content blocks
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    if not isinstance(content, str):
        raise AgentReviewError(f"unexpected model content type: {type(content)!r}")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentReviewError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise AgentReviewError("model output must be a JSON array of findings")
    return [_normalize_candidate(item) for item in raw]


def _normalize_candidate(item: Any) -> CandidateFinding:
    if not isinstance(item, dict):
        raise AgentReviewError("each finding must be a JSON object")
    finding = CandidateFinding(
        finding_ref=str(item.get("finding_ref") or ""),
        category=str(item.get("category") or "uncategorized"),
        title=str(item.get("title") or ""),
        summary=str(item.get("summary") or ""),
        severity=str(item.get("severity") or c.SEVERITY_UNKNOWN),
        confidence_band=str(item.get("confidence_band") or c.CONFIDENCE_UNKNOWN),
        is_redline=bool(item.get("is_redline") or False),
        hit_type=str(item.get("hit_type") or c.HIT_TYPE_RULE_HIT),
        locator_ids=[str(x) for x in (item.get("locator_ids") or [])],
        locator_status=str(
            item.get("locator_status") or c.LOCATOR_STATUS_UNAVAILABLE
        ),
        authority_ref_ids=[str(x) for x in (item.get("authority_ref_ids") or [])],
        limitations=[str(x) for x in (item.get("limitations") or [])],
        rule_evaluation_status=str(
            item.get("rule_evaluation_status") or c.RULE_EVAL_FAILED
        ),
    )
    if not finding["finding_ref"]:
        raise AgentReviewError("finding_ref is required for every candidate")
    return finding
