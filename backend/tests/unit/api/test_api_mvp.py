from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


SUBMITTER = {"X-Actor-ID": "submitter-1", "X-Actor-Role": "submitter"}
REVIEWER = {"X-Actor-ID": "reviewer-1", "X-Actor-Role": "reviewer"}
APPROVER = {"X-Actor-ID": "approver-1", "X-Actor-Role": "approver"}
OPERATOR = {"X-Actor-ID": "operator-1", "X-Actor-Role": "operator"}


def _create_case(client: TestClient, *, key: str = "create-case-001") -> dict:
    response = client.post(
        "/api/v1/cases",
        headers={**SUBMITTER, "Idempotency-Key": key},
        json={
            "case_reference": f"contract-{key}",
            "audit_scope_id": "scope_nda_v1",
            "contract_type": "nda",
            "business_context": {"counterparty_name": "Example Co."},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _submit_document(client: TestClient, case_id: str) -> dict:
    content = b"The customer may terminate this contract at any time."
    batch_response = client.post(
        f"/api/v1/cases/{case_id}/upload-batches",
        headers={**SUBMITTER, "Idempotency-Key": "create-batch-001"},
        json={
            "submission_note": "initial",
            "files": [
                {
                    "display_name": "contract.txt",
                    "role": "primary_contract",
                    "byte_size": len(content),
                    "declared_mime_type": "text/plain",
                }
            ],
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    batch = batch_response.json()["data"]
    upload = client.put(
        f"/api/v1/upload-sessions/{batch['files'][0]['upload_session_id']}/content",
        headers={**SUBMITTER, "Content-Type": "application/octet-stream"},
        content=content,
    )
    assert upload.status_code == 200, upload.text
    submit = client.post(
        f"/api/v1/upload-batches/{batch['upload_batch_id']}/submit",
        headers={**SUBMITTER, "Idempotency-Key": "submit-batch-001"},
        json={"expected_revision": 1, "confirm_submission": True},
    )
    assert submit.status_code == 202, submit.text
    return submit.json()["data"]


def test_health_and_authentication_envelope() -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/api/v1/cases/missing")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.json()["error"]["request_id"]


def test_create_case_is_idempotent_and_conflicting_payload_is_rejected() -> None:
    client = TestClient(create_app())
    payload = {
        "case_reference": "contract-001",
        "audit_scope_id": "scope_nda_v1",
        "contract_type": "nda",
        "business_context": {},
    }
    headers = {**SUBMITTER, "Idempotency-Key": "same-key-001"}

    first = client.post("/api/v1/cases", headers=headers, json=payload)
    replay = client.post("/api/v1/cases", headers=headers, json=payload)
    conflict = client.post(
        "/api/v1/cases", headers=headers, json={**payload, "case_reference": "other"}
    )

    assert first.status_code == replay.status_code == 201
    assert replay.json()["data"]["case_id"] == first.json()["data"]["case_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_upload_submit_creates_current_context_and_never_auto_approves() -> None:
    client = TestClient(create_app())
    case = _create_case(client)

    submitted = _submit_document(client, case["case_id"])
    overview = client.get(f"/api/v1/cases/{case['case_id']}", headers=SUBMITTER)
    result = client.get(
        f"/api/v1/cases/{case['case_id']}/audit-runs/{submitted['audit_run_id']}/result",
        headers=SUBMITTER,
    )

    assert overview.status_code == result.status_code == 200
    current = overview.json()["data"]
    assert current["current_document_version"]["document_version_id"] == submitted["document_version_id"]
    assert current["current_audit_run"]["audit_run_id"] == submitted["audit_run_id"]
    assert current["current_audit_run"]["baseline_version_id"] == "baseline_mvp_v1"
    assert current["status"] == "human_reviewing"
    assert "approved" not in result.json()["data"]
    assert result.json()["data"]["result_status"] != "approved"


def test_review_revision_and_finding_edit_does_not_resume_workflow() -> None:
    app = create_app()
    client = TestClient(app)
    case = _create_case(client)
    submitted = _submit_document(client, case["case_id"])
    queue = client.get(
        "/api/v1/review-queues/legal_review/assignments?status=queued", headers=REVIEWER
    )
    assert queue.status_code == 200, queue.text
    assignment = queue.json()["data"][0]
    assignment_id = assignment["assignment_id"]

    stale = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment_id}/accept",
        headers=REVIEWER,
        json={"expected_revision": 99, "idempotency_key": "accept-key-001"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"

    accepted = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment_id}/accept",
        headers=REVIEWER,
        json={"expected_revision": assignment["expected_revision"], "idempotency_key": "accept-key-002"},
    )
    assert accepted.status_code == 200, accepted.text
    finding = client.get(
        f"/api/v1/cases/{case['case_id']}/audit-runs/{submitted['audit_run_id']}/findings",
        headers=REVIEWER,
    ).json()["data"][0]
    adapter = app.state.audit_service.workflow_adapter
    interrupt = app.state.audit_service.hitl_store.get_interrupt(
        app.state.audit_service.hitl_store.get_assignment(assignment_id).interrupt_id
    )
    before_resume_count = len(adapter.last_snapshots)
    decision_payload = {
        "action": "edit",
        "document_version_id": submitted["document_version_id"],
        "audit_run_id": submitted["audit_run_id"],
        "baseline_version_id": "baseline_mvp_v1",
        "risk_item_id": finding["finding_id"],
        "expected_revision": accepted.json()["data"]["expected_revision"],
        "idempotency_key": "decision-edit-001",
        "reason": "exception applies",
        "evidence_refs": [],
        "payload": {"before_value": "high", "after_value": "medium"},
    }
    edited = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment_id}/decisions",
        headers=REVIEWER,
        json=decision_payload,
    )
    replay = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment_id}/decisions",
        headers=REVIEWER,
        json=decision_payload,
    )

    assert edited.status_code == replay.status_code == 201
    assert edited.json()["data"]["decision_id"] == replay.json()["data"]["decision_id"]
    assert edited.json()["data"]["case_status"] == "human_reviewing"
    assert edited.json()["data"]["finding_projection"]["status"] == "modified"
    assert len(adapter.last_snapshots) == before_resume_count
    assert interrupt.status.value == "pending"


def test_cross_context_decision_is_rejected() -> None:
    client = TestClient(create_app())
    case = _create_case(client)
    submitted = _submit_document(client, case["case_id"])
    assignment = client.get(
        "/api/v1/review-queues/legal_review/assignments?status=queued", headers=REVIEWER
    ).json()["data"][0]
    accepted = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/accept",
        headers=REVIEWER,
        json={
            "expected_revision": assignment["expected_revision"],
            "idempotency_key": "accept-context-001",
        },
    ).json()["data"]

    response = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=REVIEWER,
        json={
            "action": "reject",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": "run_from_another_context",
            "baseline_version_id": "baseline_mvp_v1",
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "decision-context-001",
            "reason": "invalid context should fail",
            "payload": {"rejection_scope": "case", "related_risk_item_ids": [], "submitter_guidance": "revise"},
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] in {"run_superseded", "stale_human_task"}


def test_approval_rejects_evidence_from_outside_the_current_run() -> None:
    app = create_app()
    client = TestClient(app)
    case = _create_case(client)
    submitted = _submit_document(client, case["case_id"])
    assignment = client.get(
        "/api/v1/review-queues/legal_review/assignments?status=queued", headers=APPROVER
    ).json()["data"][0]
    accepted = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/accept",
        headers=APPROVER,
        json={"expected_revision": 1, "idempotency_key": "accept-approve-001"},
    ).json()["data"]
    for finding in app.state.audit_service.findings.values():
        finding.status = "modified"

    response = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=APPROVER,
        json={
            "action": "approve",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": submitted["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "decision-approve-001",
            "evidence_refs": [{"type": "locator", "id": "locator_from_another_run"}],
            "payload": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_approved_case_can_create_one_idempotent_delivery_snapshot() -> None:
    app = create_app()
    client = TestClient(app)
    case = _create_case(client)
    submitted = _submit_document(client, case["case_id"])
    assignment = client.get(
        "/api/v1/review-queues/legal_review/assignments?status=queued", headers=APPROVER
    ).json()["data"][0]
    accepted = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/accept",
        headers=APPROVER,
        json={"expected_revision": 1, "idempotency_key": "accept-delivery-001"},
    ).json()["data"]
    finding = next(iter(app.state.audit_service.findings.values()))
    finding.status = "modified"
    locator_id = finding.locator_ids[0]
    approved = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=APPROVER,
        json={
            "action": "approve",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": submitted["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "decision-delivery-001",
            "evidence_refs": [{"type": "locator", "id": locator_id}],
            "payload": {"conditions": ["retain signed copy"]},
        },
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["data"]["case_status"] == "approved"
    assert app.state.audit_service.workflow_adapter.last_snapshots[submitted["audit_run_id"]].outcome == "approved"

    delivery_payload = {
        "approved_decision_id": approved.json()["data"]["decision_id"],
        "document_version_id": submitted["document_version_id"],
        "audit_run_id": submitted["audit_run_id"],
        "baseline_version_id": "baseline_mvp_v1",
        "visibility_policy": "submitter_safe",
    }
    headers = {**OPERATOR, "Idempotency-Key": "delivery-key-001"}
    first = client.post(
        f"/api/v1/cases/{case['case_id']}/deliveries", headers=headers, json=delivery_payload
    )
    replay = client.post(
        f"/api/v1/cases/{case['case_id']}/deliveries", headers=headers, json=delivery_payload
    )

    assert first.status_code == replay.status_code == 201
    assert replay.json()["data"]["delivery_id"] == first.json()["data"]["delivery_id"]
    visible = first.json()["data"]["visible_result"]
    assert "human_decisions" not in visible
    assert "approved" not in visible
