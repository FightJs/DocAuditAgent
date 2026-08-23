"""Deterministic triage / human-routing rules.

Pure functions implementing the forced-human-path criteria from
`audit_rule_hit_result_model_spec-v1.0.md` section 5.3 plus the run-level
rules from the HITL architecture spec (parse quality anomalies and incomplete
rule coverage must never be auto-routed to delivery). No LLM calls, no side
effects - kept separate from the graph nodes so the rules are trivially
unit-testable.

Nothing here ever produces "approved": the best an automated path can reach
is `ready_for_delivery`, and even that is withheld whenever any forced-human
criterion fires.
"""

from __future__ import annotations

from app.workflow import constants as c
from app.workflow.state import CandidateFinding, TriageResult


def evaluate_finding(finding: CandidateFinding) -> tuple[list[str], list[str]]:
    """Return (routing_reasons, routing_details) forcing human review.

    Each forced-human criterion from the data model maps to the fixed
    routing-reason enum; `routing_details` carries the human-readable
    explanation (including criteria that have no dedicated enum value).
    """
    reasons: list[str] = []
    details: list[str] = []
    ref = finding.get("finding_ref", "<unknown>")

    def add(reason: str, detail: str) -> None:
        if reason not in reasons:
            reasons.append(reason)
        details.append(f"{ref}: {detail}")

    if finding.get("is_redline"):
        add(c.ROUTING_REASON_REDLINE, "redline rule hit")

    severity = finding.get("severity", c.SEVERITY_UNKNOWN)
    if severity in c.SEVERITIES_FORCED_HUMAN:
        add(c.ROUTING_REASON_HIGH_SEVERITY, f"severity={severity}")

    confidence = finding.get("confidence_band", c.CONFIDENCE_UNKNOWN)
    if confidence in c.CONFIDENCE_FORCED_HUMAN:
        add(c.ROUTING_REASON_LOW_CONFIDENCE, f"confidence_band={confidence}")

    locators = finding.get("locator_ids") or []
    locator_status = finding.get("locator_status", c.LOCATOR_STATUS_UNAVAILABLE)
    if not locators or locator_status in c.LOCATOR_DEGRADED:
        add(
            c.ROUTING_REASON_EVIDENCE_GAP,
            f"missing or degraded source locators (status={locator_status})",
        )

    if not (finding.get("authority_ref_ids") or []):
        add(c.ROUTING_REASON_EVIDENCE_GAP, "no authority references")

    evaluation = finding.get("rule_evaluation_status", c.RULE_EVAL_FAILED)
    if evaluation in c.RULE_EVAL_FORCED_HUMAN:
        add(
            c.ROUTING_REASON_EVIDENCE_GAP,
            f"rule evaluation not conclusive (status={evaluation})",
        )

    hit_type = finding.get("hit_type", c.HIT_TYPE_RULE_HIT)
    if hit_type == c.HIT_TYPE_CONFLICT:
        add(c.ROUTING_REASON_RULE_CONFLICT, "conflicting rule hits")
    elif hit_type == c.HIT_TYPE_EVIDENCE_GAP:
        add(c.ROUTING_REASON_EVIDENCE_GAP, "hit_type=evidence_gap")

    if finding.get("limitations"):
        add(c.ROUTING_REASON_LOW_CONFIDENCE, "finding has explicit limitations")

    return reasons, details


def triage_run(
    *,
    findings: list[CandidateFinding],
    parse_quality_ok: bool,
    rule_coverage_complete: bool,
) -> TriageResult:
    """Aggregate finding-level results and run-level signals into a route.

    Run-level forced-human criteria (HITL spec section 9.1 decision 3):
    parse quality anomalies and incomplete rule coverage always require a
    human, including when the agent produced zero findings - an empty result
    on an incomplete baseline must never read as "no risk".
    """
    reasons: list[str] = []
    details: list[str] = []

    for finding in findings:
        f_reasons, f_details = evaluate_finding(finding)
        for reason in f_reasons:
            if reason not in reasons:
                reasons.append(reason)
        details.extend(f_details)

    if not parse_quality_ok:
        if c.ROUTING_REASON_PARSE_QUALITY not in reasons:
            reasons.append(c.ROUTING_REASON_PARSE_QUALITY)
        details.append("parse quality anomaly at document-version level")

    if not rule_coverage_complete:
        if c.ROUTING_REASON_EVIDENCE_GAP not in reasons:
            reasons.append(c.ROUTING_REASON_EVIDENCE_GAP)
        details.append("rule coverage incomplete; empty or partial results are not trustworthy")

    return TriageResult(
        requires_human=bool(reasons),
        routing_reasons=reasons,
        routing_details=details,
    )
