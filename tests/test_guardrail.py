"""Automated tests for the AI Action Guardrail platform."""
import os
import sys
import tempfile

import pytest

# Point the app at an isolated temp DB before any backend module is imported
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["GUARDRAIL_DB_PATH"] = _tmp_db.name

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402
from backend.database import db  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    db.init_db()
    yield


def _evaluate(agent_id, action_type, tool_name, parameters):
    resp = client.post(
        "/actions/evaluate",
        json={
            "agent_id": agent_id,
            "action_type": action_type,
            "tool_name": tool_name,
            "parameters": parameters,
        },
    )
    assert resp.status_code == 200
    return resp.json()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_bulk_delete_is_blocked():
    result = _evaluate("agent-A", "database_delete", "db_tool", {"record_count": 500})
    assert result["outcome"] == "block"
    assert result["execution_status"] == "not_executed"
    assert result["matched_policy"] == "bulk_delete_limit"


def test_small_delete_is_allowed():
    result = _evaluate("agent-A", "database_delete", "db_tool", {"record_count": 5})
    assert result["outcome"] == "log_and_allow"
    assert result["execution_status"] == "executed"


def test_external_email_requires_hitl():
    result = _evaluate(
        "agent-B", "send_email", "email_tool",
        {"recipient": "customer@gmail.com", "recipient_domain": "gmail.com"},
    )
    assert result["outcome"] == "require_hitl"
    assert result["execution_status"] == "pending_approval"
    assert result["matched_policy"] == "external_email_hitl"


def test_internal_email_is_allowed():
    result = _evaluate(
        "agent-B", "send_email", "email_tool",
        {"recipient": "employee@mycompany.com", "recipient_domain": "mycompany.com"},
    )
    assert result["outcome"] == "log_and_allow"
    assert result["execution_status"] == "executed"


def test_confidential_file_read_is_logged():
    result = _evaluate(
        "agent-C", "file_read", "file_tool",
        {"path": "/data/confidential/financial_report.pdf"},
    )
    assert result["outcome"] == "log_and_allow"
    assert result["matched_policy"] == "confidential_read_logging"


def test_hitl_approval_executes_the_action():
    result = _evaluate(
        "agent-D", "send_email", "email_tool",
        {"recipient": "vendor@external.com", "recipient_domain": "external.com"},
    )
    request_id = result["request_id"]
    approve_resp = client.post(f"/hitl/{request_id}/approve", json={"decided_by": "reviewer1"})
    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["decision"] == "approved"
    assert body["execution_status"] == "approved_executed"

    records = client.get(f"/audit-logs/{request_id}").json()
    assert records[-1]["execution_status"] == "approved_executed"
    assert records[-1]["human_decision"] == "approved_by:reviewer1"


def test_hitl_rejection_does_not_execute():
    result = _evaluate(
        "agent-D", "send_email", "email_tool",
        {"recipient": "vendor2@external.com", "recipient_domain": "external.com"},
    )
    request_id = result["request_id"]
    reject_resp = client.post(f"/hitl/{request_id}/reject", json={"decided_by": "reviewer2"})
    assert reject_resp.status_code == 200
    assert reject_resp.json()["execution_status"] == "rejected"

    records = client.get(f"/audit-logs/{request_id}").json()
    assert records[-1]["execution_status"] == "rejected"
    assert records[-1]["execution_result"] is None


def test_audit_logs_are_created():
    before = len(client.get("/audit-logs").json())
    _evaluate("agent-E", "database_read", "db_tool", {"table": "orders"})
    after = len(client.get("/audit-logs").json())
    assert after == before + 1


def test_unknown_action_follows_default_policy():
    # database_read has no explicit policy defined -> safe default: log_and_allow
    result = _evaluate("agent-F", "database_read", "db_tool", {"table": "customers"})
    assert result["outcome"] == "log_and_allow"
    assert result["matched_policy"] is None
    assert result["execution_status"] == "executed"


def test_policy_priority_block_beats_others():
    """A record_count above the threshold should always block, regardless of
    any other matching low-priority rule (demonstrates fail-closed priority)."""
    result = _evaluate("agent-A", "database_delete", "db_tool", {"record_count": 1000})
    assert result["outcome"] == "block"


def test_demo_endpoint_runs_real_flow():
    resp = client.post("/demo/run")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 5
    assert all(r["passed"] for r in results)


def test_sensitive_parameters_are_redacted():
    result = _evaluate(
        "agent-G", "send_email", "email_tool",
        {"recipient": "internal@mycompany.com", "recipient_domain": "mycompany.com", "password": "supersecret"},
    )
    records = client.get(f"/audit-logs/{result['request_id']}").json()
    assert records[-1]["parameters"]["password"] == "***REDACTED***"
