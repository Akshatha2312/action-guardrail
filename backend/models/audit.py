"""Audit event schema - the persisted record of every evaluated action."""
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AuditEvent(BaseModel):
    event_id: str
    request_id: str
    agent_id: str
    session_id: str
    timestamp: str
    action_type: str
    tool_name: str
    parameters: Dict[str, Any]
    matched_policy: Optional[str]
    outcome: str
    execution_status: str
    human_decision: Optional[str]
    reason: str
    execution_result: Optional[Dict[str, Any]] = None
