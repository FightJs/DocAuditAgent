"""Tests for the LLM adapter layer: env settings, client construction
parameters (offline, no network) and response parsing/normalization."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from app.workflow import constants as c
from app.workflow.llm import (
    AgentReviewError,
    LLMAgentReviewer,
    WorkflowConfigError,
    build_chat_model,
    parse_findings_json,
)
from app.workflow.settings import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    WorkflowLLMSettings,
)
from app.workflow.state import ReviewRequest


def make_request() -> ReviewRequest:
    return ReviewRequest(
        case_id="case_01",
        document_version_id="docv_01",
        audit_run_id="run_01",
        baseline_version_id="baseline_2026_01",
        parsed_document={"clauses": [{"clause_id": "1", "text": "保密义务"}]},
    )


# -- settings --------------------------------------------------------------


def test_settings_defaults_match_plan():
    settings = WorkflowLLMSettings.from_env({})
    assert settings.base_url == DEFAULT_BASE_URL == "https://api.deepseek.com"
    assert settings.model == DEFAULT_MODEL == "deepseek-v4-flash"
    assert settings.api_key is None


def test_settings_env_overrides():
    settings = WorkflowLLMSettings.from_env(
        {
            "DEEPSEEK_BASE_URL": "https://example.internal",
            "DEEPSEEK_MODEL": "deepseek-v4-pro",
            "DEEPSEEK_API_KEY": "test-key-not-real",
        }
    )
    assert settings.base_url == "https://example.internal"
    assert settings.model == "deepseek-v4-pro"
    assert settings.api_key == "test-key-not-real"


def test_settings_empty_key_becomes_none():
    assert WorkflowLLMSettings.from_env({"DEEPSEEK_API_KEY": ""}).api_key is None


# -- client construction (offline) -----------------------------------------


def test_build_chat_model_requires_api_key():
    with pytest.raises(WorkflowConfigError):
        build_chat_model(WorkflowLLMSettings())


def test_build_chat_model_uses_settings_without_network():
    model = build_chat_model(
        WorkflowLLMSettings(
            base_url="https://example.internal", model="m-x", api_key="k-test"
        )
    )
    assert model.model_name == "m-x"
    assert str(model.openai_api_base) == "https://example.internal"
    assert model.openai_api_key.get_secret_value() == "k-test"


# -- reviewer with fake chat model (offline) --------------------------------


def test_llm_reviewer_parses_json_findings():
    payload = (
        '[{"finding_ref": "cand-1", "category": "liability",'
        ' "title": "uncapped liability", "severity": "high",'
        ' "confidence_band": "medium", "is_redline": false,'
        ' "hit_type": "rule_hit", "locator_ids": ["loc-1"],'
        ' "locator_status": "ok", "authority_ref_ids": ["auth-1"],'
        ' "limitations": [], "rule_evaluation_status": "passed"}]'
    )
    chat = GenericFakeChatModel(messages=iter([payload]))
    findings = LLMAgentReviewer(chat).review(make_request())
    assert len(findings) == 1
    assert findings[0]["finding_ref"] == "cand-1"
    assert findings[0]["severity"] == c.SEVERITY_HIGH


def test_llm_reviewer_empty_array_for_no_findings():
    chat = GenericFakeChatModel(messages=iter(["[]"]))
    assert LLMAgentReviewer(chat).review(make_request()) == []


def test_llm_reviewer_wraps_sdk_errors_as_agent_review_error():
    class ExplodingChat:
        def invoke(self, messages):
            raise ConnectionError("boom")

    with pytest.raises(AgentReviewError):
        LLMAgentReviewer(ExplodingChat()).review(make_request())


# -- parsing / normalization ------------------------------------------------


def test_parse_findings_json_strips_code_fences():
    findings = parse_findings_json(
        '```json\n[{"finding_ref": "cand-9", "severity": "low",'
        ' "confidence_band": "high", "locator_ids": ["l"],'
        ' "locator_status": "ok", "authority_ref_ids": ["a"],'
        ' "rule_evaluation_status": "passed"}]\n```'
    )
    assert findings[0]["finding_ref"] == "cand-9"


def test_parse_findings_json_rejects_non_array():
    with pytest.raises(AgentReviewError):
        parse_findings_json('{"finding_ref": "x"}')


def test_parse_findings_json_rejects_invalid_json():
    with pytest.raises(AgentReviewError):
        parse_findings_json("not json at all")


def test_parse_findings_json_rejects_non_object_items():
    with pytest.raises(AgentReviewError):
        parse_findings_json('["just-a-string"]')


def test_missing_fields_normalize_to_conservative_values():
    """Malformed model output must force human review downstream, never
    silently auto-pass."""
    findings = parse_findings_json('[{"finding_ref": "cand-2"}]')
    finding = findings[0]
    assert finding["severity"] == c.SEVERITY_UNKNOWN
    assert finding["confidence_band"] == c.CONFIDENCE_UNKNOWN
    assert finding["locator_status"] == c.LOCATOR_STATUS_UNAVAILABLE
    assert finding["rule_evaluation_status"] == c.RULE_EVAL_FAILED
    assert finding["locator_ids"] == []
    assert finding["authority_ref_ids"] == []


def test_missing_finding_ref_is_rejected():
    with pytest.raises(AgentReviewError):
        parse_findings_json('[{"severity": "low"}]')
