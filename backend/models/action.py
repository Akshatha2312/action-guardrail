"""Standard action schema that every agent tool-call must conform to."""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    DATABASE_DELETE = "database_delete"
    DATABASE_READ = "database_read"
    SEND_EMAIL = "send_email"
    FILE_READ = "file_read"


class Outcome(str, Enum):
    BLOCK = "block"
    REQUIRE_HITL = "require_hitl"
    LOG_AND_ALLOW = "log_and_allow"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "not_executed"
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED_EXECUTED = "approved_executed"
    REJECTED = "rejected"
    EXECUTION_FAILED = "execution_failed"


class ActionRequest(BaseModel):
    """Incoming action/tool-call submitted by an agent for evaluation."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        use_enum_values = True


class EvaluationResult(BaseModel):
    """Result returned immediately after policy evaluation (before/without execution)."""

    request_id: str
    agent_id: str
    session_id: str
    action_type: str
    tool_name: str
    outcome: Outcome
    matched_policy: Optional[str] = None
    reason: str
    execution_status: ExecutionStatus
    execution_result: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True


class HitlDecisionRequest(BaseModel):
    decided_by: str = "human_reviewer"
    comment: Optional[str] = None
