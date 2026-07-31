"""AI Action Guardrail & Governance Platform - FastAPI backend."""
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config.logging_config import logger
from backend.database import db
from backend.guardrails import evaluator
from backend.guardrails.evaluator import policy_engine
from backend.models.action import ActionRequest, EvaluationResult, HitlDecisionRequest

app = FastAPI(
    title="AI Action Guardrail & Governance Platform",
    description="Evaluates agent tool-calls/actions against a policy engine before execution.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    logger.info("AI Action Guardrail backend started.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/actions/evaluate", response_model=EvaluationResult)
def evaluate_action(action: ActionRequest):
    """Evaluate (and, if permitted, execute) an action through the full guardrail flow."""
    try:
        return evaluator.evaluate_and_process(action)
    except Exception as e:
        logger.error(f"Error evaluating action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/actions/execute", response_model=EvaluationResult)
def execute_action(action: ActionRequest):
    """Alias of /actions/evaluate - every action must pass through the guardrail
    before it can ever be executed, so 'execute' and 'evaluate' share one code path."""
    return evaluate_action(action)


@app.get("/audit-logs")
def audit_logs(limit: int = 200):
    return db.get_all_audit_logs(limit=limit)


@app.get("/audit-logs/{request_id}")
def audit_logs_for_request(request_id: str):
    records = db.get_audit_by_request_id(request_id)
    if not records:
        raise HTTPException(status_code=404, detail="No audit records found for this request_id")
    return records


@app.get("/hitl/pending")
def hitl_pending():
    return db.get_pending_hitl()


@app.post("/hitl/{request_id}/approve")
def hitl_approve(request_id: str, decision: HitlDecisionRequest = HitlDecisionRequest()):
    try:
        return evaluator.process_hitl_decision(request_id, approve=True, decided_by=decision.decided_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/hitl/{request_id}/reject")
def hitl_reject(request_id: str, decision: HitlDecisionRequest = HitlDecisionRequest()):
    try:
        return evaluator.process_hitl_decision(request_id, approve=False, decided_by=decision.decided_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/policies")
def list_policies():
    return {"internal_domains": policy_engine.internal_domains, "policies": policy_engine.rules}


@app.get("/metrics")
def metrics():
    return db.get_metrics()


DEMO_SCENARIOS = [
    {"agent_id": "agent-A", "action_type": "database_delete", "tool_name": "db_tool",
     "parameters": {"record_count": 500}, "expected": "block"},
    {"agent_id": "agent-A", "action_type": "database_delete", "tool_name": "db_tool",
     "parameters": {"record_count": 5}, "expected": "log_and_allow"},
    {"agent_id": "agent-B", "action_type": "send_email", "tool_name": "email_tool",
     "parameters": {"recipient": "customer@gmail.com", "recipient_domain": "gmail.com", "subject": "Invoice"},
     "expected": "require_hitl"},
    {"agent_id": "agent-B", "action_type": "send_email", "tool_name": "email_tool",
     "parameters": {"recipient": "employee@mycompany.com", "recipient_domain": "mycompany.com", "subject": "Standup notes"},
     "expected": "log_and_allow"},
    {"agent_id": "agent-C", "action_type": "file_read", "tool_name": "file_tool",
     "parameters": {"path": "/data/confidential/financial_report.pdf"}, "expected": "log_and_allow"},
]


@app.post("/demo/run")
def run_demo() -> List[dict]:
    """Runs the required demo scenarios through the REAL guardrail evaluation flow
    (no hardcoded results) and returns pass/fail against expected outcomes."""
    results = []
    for scenario in DEMO_SCENARIOS:
        action = ActionRequest(
            agent_id=scenario["agent_id"],
            action_type=scenario["action_type"],
            tool_name=scenario["tool_name"],
            parameters=scenario["parameters"],
        )
        result = evaluator.evaluate_and_process(action)
        results.append({
            "agent_id": scenario["agent_id"],
            "action_type": scenario["action_type"],
            "parameters": scenario["parameters"],
            "expected_outcome": scenario["expected"],
            "actual_outcome": result.outcome,
            "passed": result.outcome == scenario["expected"],
            "matched_policy": result.matched_policy,
            "execution_status": result.execution_status,
            "request_id": result.request_id,
        })
    return results
