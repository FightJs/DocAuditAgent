"""Offline API-level end-to-end tests for the backend MVP's primary flows."""

from __future__ import annotations

from fastapi.testclient import TestClient


SUBMITTER = {"X-Actor-ID": "submitter-e2e", "X-Actor-Role": "submitter"}
REVIEWER = {"X-Actor-ID": "reviewer-e2e", "X-Actor-Role": "reviewer"}
APPROVER = {"X-Actor-ID": "approver-e2e", "X-Actor-Role": "approver"}
OPERATOR = {"X-Actor-ID": "operator-e2e", "X-Actor-Role": "operator"}


def _create_case(client: TestClient, key: str) -> dict:
    response = client.post(
        "/api/v1/cases",
        headers={**SUBMITTER, "Idempotency-Key": f"case-{key}"},
        json={
            "case_reference": f"e2e-contract-{key}",
            "audit_scope_id": "scope_nda_v1",
            "contract_type": "nda",
            "business_context": {"counterparty_name": "E2E Counterparty"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _upload_and_submit(
    client: TestClient, case_id: str, key: str, *, parent_document_version_id: str | None = None
) -> dict:
    content = f"The counterparty may terminate at any time. ({key})".encode()
    batch = client.post(
        f"/api/v1/cases/{case_id}/upload-batches",
        headers={**SUBMITTER, "Idempotency-Key": f"batch-{key}"},
        json={
            "submission_note": f"e2e upload {key}",
            "parent_document_version_id": parent_document_version_id,
            "files": [
                {
                    "display_name": f"contract-{key}.txt",
                    "role": "primary_contract",
                    "byte_size": len(content),
                    "declared_mime_type": "text/plain",
                }
            ],
        },
    )
    assert batch.status_code == 201, batch.text
    batch_data = batch.json()["data"]
    uploaded = client.put(
        f"/api/v1/upload-sessions/{batch_data['files'][0]['upload_session_id']}/content",
        headers=SUBMITTER,
        content=content,
    )
    assert uploaded.status_code == 200, uploaded.text
    submitted = client.post(
        f"/api/v1/upload-batches/{batch_data['upload_batch_id']}/submit",
        headers={**SUBMITTER, "Idempotency-Key": f"submit-{key}"},
        json={"expected_revision": 1, "confirm_submission": True},
    )
    assert submitted.status_code == 202, submitted.text
    return submitted.json()["data"]


def _queued_assignment(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get(
        "/api/v1/review-queues/legal_review/assignments?status=queued", headers=headers
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 1
    return response.json()["data"][0]


def _accept(client: TestClient, case_id: str, assignment: dict, headers: dict[str, str], key: str) -> dict:
    response = client.post(
        f"/api/v1/cases/{case_id}/assignments/{assignment['assignment_id']}/accept",
        headers=headers,
        json={"expected_revision": assignment["expected_revision"], "idempotency_key": f"accept-{key}"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _find_one(client: TestClient, case_id: str, run_id: str, headers: dict[str, str]) -> dict:
    response = client.get(
        f"/api/v1/cases/{case_id}/audit-runs/{run_id}/findings", headers=headers
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 1
    return response.json()["data"][0]


def test_submit_review_approve_and_deliver_full_flow(client: TestClient) -> None:
    case = _create_case(client, "approve")
    submitted = _upload_and_submit(client, case["case_id"], "approve")
    assignment = _queued_assignment(client, APPROVER)
    accepted = _accept(client, case["case_id"], assignment, APPROVER, "approve")
    finding = _find_one(client, case["case_id"], submitted["audit_run_id"], APPROVER)

    edited = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=APPROVER,
        json={
            "action": "edit",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": submitted["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
            "risk_item_id": finding["finding_id"],
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "edit-approve-001",
            "reason": "已确认例外适用范围",
            "payload": {"before_value": "high", "after_value": "medium"},
        },
    )
    assert edited.status_code == 201, edited.text

    detail = client.get(
        f"/api/v1/cases/{case['case_id']}/audit-runs/{submitted['audit_run_id']}/findings/{finding['finding_id']}",
        headers=APPROVER,
    )
    locator_id = detail.json()["data"]["source_locator"]["locator_id"]
    approved_payload = {
        "action": "approve",
        "document_version_id": submitted["document_version_id"],
        "audit_run_id": submitted["audit_run_id"],
        "baseline_version_id": "baseline_mvp_v1",
        "expected_revision": edited.json()["data"]["expected_revision"],
        "idempotency_key": "approve-e2e-001",
        "evidence_refs": [{"type": "locator", "id": locator_id}],
        "payload": {"conditions": ["保留签署版本"]},
    }
    approved = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=APPROVER,
        json=approved_payload,
    )
    approval_replay = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=APPROVER,
        json=approved_payload,
    )
    assert approved.status_code == approval_replay.status_code == 201
    assert approved.json()["data"]["decision_id"] == approval_replay.json()["data"]["decision_id"]
    assert approved.json()["data"]["case_status"] == "approved"

    delivery_payload = {
        "approved_decision_id": approved.json()["data"]["decision_id"],
        "document_version_id": submitted["document_version_id"],
        "audit_run_id": submitted["audit_run_id"],
        "baseline_version_id": "baseline_mvp_v1",
        "visibility_policy": "submitter_safe",
    }
    delivery = client.post(
        f"/api/v1/cases/{case['case_id']}/deliveries",
        headers={**OPERATOR, "Idempotency-Key": "delivery-e2e-001"},
        json=delivery_payload,
    )
    assert delivery.status_code == 201, delivery.text
    assert delivery.json()["data"]["delivery_status"] == "delivered"
    assert client.get(f"/api/v1/cases/{case['case_id']}", headers=SUBMITTER).json()["data"]["status"] == "delivered"


def test_reviewer_requests_supplement_and_submitter_sees_material_request(client: TestClient) -> None:
    case = _create_case(client, "supplement")
    submitted = _upload_and_submit(client, case["case_id"], "supplement")
    assignment = _queued_assignment(client, REVIEWER)
    accepted = _accept(client, case["case_id"], assignment, REVIEWER, "supplement")

    response = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=REVIEWER,
        json={
            "action": "request_supplement",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": submitted["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "supplement-e2e-001",
            "reason": "需提供签署页以完成核验",
            "payload": {"requested_supplements": ["签署页"], "purpose": "核验签署主体"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["case_status"] == "changes_requested"
    requests = client.get(
        f"/api/v1/cases/{case['case_id']}/document-versions/{submitted['document_version_id']}/material-requests",
        headers=SUBMITTER,
    )
    assert requests.status_code == 200, requests.text
    assert requests.json()["data"][0]["missing_items"] == ["签署页"]


def test_authorization_and_stale_revision_are_rejected(client: TestClient) -> None:
    case = _create_case(client, "auth")
    submitted = _upload_and_submit(client, case["case_id"], "auth")
    assert client.get("/api/v1/review-queues/legal_review/assignments", headers=SUBMITTER).status_code == 403
    assignment = _queued_assignment(client, REVIEWER)
    stale = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/accept",
        headers=REVIEWER,
        json={"expected_revision": assignment["expected_revision"] + 1, "idempotency_key": "stale-e2e-001"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"
    forbidden_delivery = client.post(
        f"/api/v1/cases/{case['case_id']}/deliveries",
        headers={**REVIEWER, "Idempotency-Key": "forbidden-delivery"},
        json={
            "approved_decision_id": "decision_unavailable",
            "document_version_id": submitted["document_version_id"],
            "audit_run_id": submitted["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
        },
    )
    assert forbidden_delivery.status_code == 403
    assert forbidden_delivery.json()["error"]["code"] == "action_not_authorized"


def test_new_submission_supersedes_old_assignment_context(client: TestClient) -> None:
    case = _create_case(client, "supersede")
    first = _upload_and_submit(client, case["case_id"], "supersede-v1")
    assignment = _queued_assignment(client, REVIEWER)
    accepted = _accept(client, case["case_id"], assignment, REVIEWER, "supersede")
    second = _upload_and_submit(
        client,
        case["case_id"],
        "supersede-v2",
        parent_document_version_id=first["document_version_id"],
    )

    old_decision = client.post(
        f"/api/v1/cases/{case['case_id']}/assignments/{assignment['assignment_id']}/decisions",
        headers=REVIEWER,
        json={
            "action": "request_supplement",
            "document_version_id": first["document_version_id"],
            "audit_run_id": first["audit_run_id"],
            "baseline_version_id": "baseline_mvp_v1",
            "expected_revision": accepted["expected_revision"],
            "idempotency_key": "old-context-e2e-001",
            "reason": "旧版本不应再被处理",
            "payload": {"requested_supplements": ["旧版本材料"]},
        },
    )
    assert old_decision.status_code == 409
    assert old_decision.json()["error"]["code"] in {"run_superseded", "stale_human_task"}
    current = client.get(f"/api/v1/cases/{case['case_id']}", headers=SUBMITTER)
    assert current.json()["data"]["current_audit_run"]["audit_run_id"] == second["audit_run_id"]
