"""Unit tests for the deterministic forced-human triage rules.

Covers every criterion from audit_rule_hit_result_model_spec section 5.3 plus
the run-level parse-quality / rule-coverage rules. No LangGraph, no LLM.
"""

from __future__ import annotations

from app.workflow import constants as c
from app.workflow.state import CandidateFinding
from app.workflow.triage import evaluate_finding, triage_run


def clean_finding(**overrides) -> CandidateFinding:
    """A finding that must NOT trigger any forced-human criterion."""
    base = CandidateFinding(
        finding_ref="cand-1",
        category="liability",
        title="limitation of liability cap",
        summary="cap below baseline",
        severity=c.SEVERITY_LOW,
        confidence_band=c.CONFIDENCE_HIGH,
        is_redline=False,
        hit_type=c.HIT_TYPE_RULE_HIT,
        locator_ids=["loc-1"],
        locator_status=c.LOCATOR_STATUS_OK,
        authority_ref_ids=["auth-1"],
        limitations=[],
        rule_evaluation_status=c.RULE_EVAL_PASSED,
    )
    base.update(overrides)
    return base


def test_clean_finding_does_not_require_human():
    reasons, details = evaluate_finding(clean_finding())
    assert reasons == []
    assert details == []


def test_redline_forces_human():
    reasons, _ = evaluate_finding(clean_finding(is_redline=True))
    assert c.ROUTING_REASON_REDLINE in reasons


def test_critical_and_high_severity_force_human():
    for severity in (c.SEVERITY_CRITICAL, c.SEVERITY_HIGH):
        reasons, _ = evaluate_finding(clean_finding(severity=severity))
        assert c.ROUTING_REASON_HIGH_SEVERITY in reasons


def test_medium_severity_alone_does_not_force_human():
    reasons, _ = evaluate_finding(clean_finding(severity=c.SEVERITY_MEDIUM))
    assert c.ROUTING_REASON_HIGH_SEVERITY not in reasons


def test_low_and_unknown_confidence_force_human():
    for band in (c.CONFIDENCE_LOW, c.CONFIDENCE_UNKNOWN):
        reasons, _ = evaluate_finding(clean_finding(confidence_band=band))
        assert c.ROUTING_REASON_LOW_CONFIDENCE in reasons


def test_missing_locators_force_human():
    reasons, _ = evaluate_finding(clean_finding(locator_ids=[]))
    assert c.ROUTING_REASON_EVIDENCE_GAP in reasons


def test_degraded_locators_force_human():
    for status in (c.LOCATOR_STATUS_STALE, c.LOCATOR_STATUS_UNAVAILABLE):
        reasons, _ = evaluate_finding(clean_finding(locator_status=status))
        assert c.ROUTING_REASON_EVIDENCE_GAP in reasons


def test_approximate_locator_alone_does_not_force_human():
    reasons, _ = evaluate_finding(
        clean_finding(locator_status=c.LOCATOR_STATUS_APPROXIMATE)
    )
    assert c.ROUTING_REASON_EVIDENCE_GAP not in reasons


def test_missing_authority_refs_force_human():
    reasons, _ = evaluate_finding(clean_finding(authority_ref_ids=[]))
    assert c.ROUTING_REASON_EVIDENCE_GAP in reasons


def test_inconclusive_rule_evaluation_forces_human():
    for status in (c.RULE_EVAL_INCONCLUSIVE, c.RULE_EVAL_FAILED, c.RULE_EVAL_SKIPPED):
        reasons, _ = evaluate_finding(clean_finding(rule_evaluation_status=status))
        assert c.ROUTING_REASON_EVIDENCE_GAP in reasons


def test_rule_conflict_hit_type_forces_human():
    reasons, _ = evaluate_finding(clean_finding(hit_type=c.HIT_TYPE_CONFLICT))
    assert c.ROUTING_REASON_RULE_CONFLICT in reasons


def test_evidence_gap_hit_type_forces_human():
    reasons, _ = evaluate_finding(clean_finding(hit_type=c.HIT_TYPE_EVIDENCE_GAP))
    assert c.ROUTING_REASON_EVIDENCE_GAP in reasons


def test_limitations_force_human():
    reasons, _ = evaluate_finding(clean_finding(limitations=["OCR quality low"]))
    assert c.ROUTING_REASON_LOW_CONFIDENCE in reasons


def test_unknown_fields_default_to_conservative_human_route():
    """A bare finding_ref must be treated as untrusted, never auto-passed."""
    reasons, _ = evaluate_finding(CandidateFinding(finding_ref="cand-x"))
    assert c.ROUTING_REASON_EVIDENCE_GAP in reasons
    assert c.ROUTING_REASON_LOW_CONFIDENCE in reasons


def test_run_level_clean_passes_without_human():
    result = triage_run(
        findings=[clean_finding()],
        parse_quality_ok=True,
        rule_coverage_complete=True,
    )
    assert result["requires_human"] is False
    assert result["routing_reasons"] == []


def test_parse_quality_anomaly_forces_human_even_with_zero_findings():
    result = triage_run(
        findings=[],
        parse_quality_ok=False,
        rule_coverage_complete=True,
    )
    assert result["requires_human"] is True
    assert c.ROUTING_REASON_PARSE_QUALITY in result["routing_reasons"]


def test_incomplete_rule_coverage_forces_human_even_with_zero_findings():
    """Empty findings on incomplete coverage must never read as no-risk."""
    result = triage_run(
        findings=[],
        parse_quality_ok=True,
        rule_coverage_complete=False,
    )
    assert result["requires_human"] is True
    assert c.ROUTING_REASON_EVIDENCE_GAP in result["routing_reasons"]


def test_reasons_deduplicated_across_findings():
    result = triage_run(
        findings=[
            clean_finding(finding_ref="a", is_redline=True),
            clean_finding(finding_ref="b", is_redline=True),
        ],
        parse_quality_ok=True,
        rule_coverage_complete=True,
    )
    assert result["routing_reasons"].count(c.ROUTING_REASON_REDLINE) == 1
    assert len(result["routing_details"]) == 2
