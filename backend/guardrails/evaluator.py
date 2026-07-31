"""Guardrail Evaluator - orchestrates the full action lifecycle.

Flow:
 1. Receive action (already validated by Pydantic at the API layer)
 2. Load active policies (PolicyEngine)
 3. Evaluate policies against the action
 4. Identify matching rule(s) and resolve priority
 5. Determine outcome
 6. Write audit event
 7. BLOCK -> do not execute
    REQUIRE_HITL -> store as pending
    LOG_AND_ALLOW / no match (default) -> execute tool
 8. Record final execution result
"""
from typing import Any, Dict

from backend.config.logging_config import logger
from backend.database import db
from backend.guardrails.policy_engine import PolicyEngine
from backend.models.action import ActionRequest, EvaluationResult, ExecutionStatus, Outcome
from backend.tools.simulator import ToolExecutor

# Singletons - shared policy engine (hot-reloadable) and tool executor
policy_engine = PolicyEngine()
tool_executor = ToolExecutor()

DEFAULT_OUTCOME = Outcome.LOG_AND_ALLOW
DEFAULT_REASON = "No policy rule matched this action - default safe policy applied (log and allow)."


def evaluate_and_process(action: ActionRequest) -> EvaluationResult:
    """Evaluate an action against policy and execute it if permitted."""
    parameters = action.parameters

    matches = policy_engine.evaluate(action.action_type, parameters)
    winning_rule = policy_engine.resolve(matches)

    if winning_rule:
        outcome = Outcome(winning_rule.outcome)
        matched_policy = winning_rule.id
        reason = winning_rule.description
    else:
        outcome = DEFAULT_OUTCOME
        matched_policy = None
        reason = DEFAULT_REASON

    execution_result: Dict[str, Any] = None
    execution_status: ExecutionStatus

    if outcome == Outcome.BLOCK:
        execution_status = ExecutionStatus.NOT_EXECUTED
        logger.info(f"[BLOCK] request_id={action.request_id} rule={matched_policy}")

    elif outcome == Outcome.REQUIRE_HITL:
        execution_status = ExecutionStatus.PENDING_APPROVAL
        logger.info(f"[REQUIRE_HITL] request_id={action.request_id} rule={matched_policy}")

    else:  # LOG_AND_ALLOW
        execution_status, execution_result = _execute(action)
        logger.info(f"[LOG_AND_ALLOW] request_id={action.request_id} rule={matched_policy}")

    db.insert_audit_event(
        request_id=action.request_id,
        agent_id=action.agent_id,
        session_id=action.session_id,
        action_type=action.action_type,
        tool_name=action.tool_name,
        parameters=parameters,
        matched_policy=matched_policy,
        outcome=outcome.value,
        execution_status=execution_status.value,
        reason=reason,
        execution_result=execution_result,
    )

    return EvaluationResult(
        request_id=action.request_id,
        agent_id=action.agent_id,
        session_id=action.session_id,
        action_type=action.action_type,
        tool_name=action.tool_name,
        outcome=outcome,
        matched_policy=matched_policy,
        reason=reason,
        execution_status=execution_status,
        execution_result=execution_result,
    )


def _execute(action: ActionRequest):
    try:
        result = tool_executor.execute(action.action_type, action.parameters)
        return ExecutionStatus.EXECUTED, result
    except Exception as e:
        logger.error(f"Execution failed for request_id={action.request_id}: {e}")
        return ExecutionStatus.EXECUTION_FAILED, {"status": "error", "message": str(e)}


def process_hitl_decision(request_id: str, approve: bool, decided_by: str) -> Dict[str, Any]:
    """Apply a human decision to a pending HITL action."""
    records = db.get_audit_by_request_id(request_id)
    if not records:
        raise ValueError(f"No audit record found for request_id={request_id}")

    record = records[-1]
    if record["outcome"] != "require_hitl":
        raise ValueError("This action was not flagged for HITL review")
    if record["execution_status"] != "pending_approval":
        raise ValueError(f"Action already resolved (status={record['execution_status']})")

    if approve:
        fake_action = ActionRequest(
            request_id=record["request_id"],
            agent_id=record["agent_id"],
            session_id=record["session_id"],
            action_type=record["action_type"],
            tool_name=record["tool_name"],
            parameters=record["parameters"],
        )
        status, result = _execute(fake_action)
        final_status = ExecutionStatus.APPROVED_EXECUTED.value if status == ExecutionStatus.EXECUTED else status.value
        db.update_execution(
            request_id=request_id,
            execution_status=final_status,
            human_decision=f"approved_by:{decided_by}",
            execution_result=result,
        )
        logger.info(f"[HITL APPROVED] request_id={request_id} by={decided_by}")
        return {"request_id": request_id, "decision": "approved", "execution_status": final_status, "execution_result": result}
    else:
        db.update_execution(
            request_id=request_id,
            execution_status=ExecutionStatus.REJECTED.value,
            human_decision=f"rejected_by:{decided_by}",
        )
        logger.info(f"[HITL REJECTED] request_id={request_id} by={decided_by}")
        return {"request_id": request_id, "decision": "rejected", "execution_status": ExecutionStatus.REJECTED.value}
