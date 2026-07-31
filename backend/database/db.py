"""SQLite persistence for audit events.

Plain sqlite3 (no ORM) is used intentionally to keep the code easy to
read and explain, per project constraints.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config.settings import DB_PATH, SENSITIVE_PARAM_KEYS

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    action_type TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    parameters TEXT NOT NULL,
    matched_policy TEXT,
    outcome TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    human_decision TEXT,
    reason TEXT,
    execution_result TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA)


def sanitize_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive parameter values before they are ever persisted/displayed."""
    sanitized = {}
    for k, v in parameters.items():
        if k.lower() in SENSITIVE_PARAM_KEYS:
            sanitized[k] = "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized


def insert_audit_event(
    request_id: str,
    agent_id: str,
    session_id: str,
    action_type: str,
    tool_name: str,
    parameters: Dict[str, Any],
    matched_policy: Optional[str],
    outcome: str,
    execution_status: str,
    reason: str,
    human_decision: Optional[str] = None,
    execution_result: Optional[Dict[str, Any]] = None,
) -> str:
    event_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audit_events
               (event_id, request_id, agent_id, session_id, timestamp, action_type,
                tool_name, parameters, matched_policy, outcome, execution_status,
                human_decision, reason, execution_result)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                request_id,
                agent_id,
                session_id,
                datetime.now(timezone.utc).isoformat(),
                action_type,
                tool_name,
                json.dumps(sanitize_parameters(parameters)),
                matched_policy,
                outcome,
                execution_status,
                human_decision,
                reason,
                json.dumps(execution_result) if execution_result is not None else None,
            ),
        )
    return event_id


def update_execution(
    request_id: str,
    execution_status: str,
    human_decision: Optional[str] = None,
    execution_result: Optional[Dict[str, Any]] = None,
) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE audit_events
               SET execution_status = ?,
                   human_decision = COALESCE(?, human_decision),
                   execution_result = COALESCE(?, execution_result)
               WHERE request_id = ?""",
            (
                execution_status,
                human_decision,
                json.dumps(execution_result) if execution_result is not None else None,
                request_id,
            ),
        )
        return cur.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["parameters"] = json.loads(d["parameters"]) if d["parameters"] else {}
    d["execution_result"] = json.loads(d["execution_result"]) if d["execution_result"] else None
    return d


def get_all_audit_logs(limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_audit_by_request_id(request_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE request_id = ? ORDER BY timestamp", (request_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_pending_hitl() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM audit_events
               WHERE outcome = 'require_hitl' AND execution_status = 'pending_approval'
               ORDER BY timestamp"""
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_metrics() -> Dict[str, int]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM audit_events").fetchone()["c"]
        allowed = conn.execute(
            "SELECT COUNT(*) c FROM audit_events WHERE outcome = 'log_and_allow'"
        ).fetchone()["c"]
        blocked = conn.execute(
            "SELECT COUNT(*) c FROM audit_events WHERE outcome = 'block'"
        ).fetchone()["c"]
        hitl_pending = conn.execute(
            """SELECT COUNT(*) c FROM audit_events
               WHERE outcome = 'require_hitl' AND execution_status = 'pending_approval'"""
        ).fetchone()["c"]
        hitl_total = conn.execute(
            "SELECT COUNT(*) c FROM audit_events WHERE outcome = 'require_hitl'"
        ).fetchone()["c"]
    return {
        "total_evaluated": total,
        "allowed": allowed,
        "blocked": blocked,
        "hitl_pending": hitl_pending,
        "hitl_total": hitl_total,
    }
