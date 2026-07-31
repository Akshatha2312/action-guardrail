"""Mock tools used to simulate real-world agent actions safely.

None of these touch a real database, send a real email, or read a real
file. They exist purely so the guardrail's ALLOW path can be demonstrated
end-to-end without side effects.
"""
import random
from typing import Any, Dict

from backend.config.logging_config import logger


class MockDatabaseTool:
    @staticmethod
    def delete(parameters: Dict[str, Any]) -> Dict[str, Any]:
        count = parameters.get("record_count", 0)
        logger.info(f"[MockDatabaseTool] Simulating delete of {count} records")
        return {
            "status": "success",
            "message": f"Simulated deletion of {count} records (no real data affected)",
            "records_deleted": count,
        }

    @staticmethod
    def read(parameters: Dict[str, Any]) -> Dict[str, Any]:
        table = parameters.get("table", "unknown_table")
        logger.info(f"[MockDatabaseTool] Simulating read from {table}")
        return {
            "status": "success",
            "message": f"Simulated read from table '{table}'",
            "rows_returned": random.randint(1, 20),
        }


class MockEmailTool:
    @staticmethod
    def send(parameters: Dict[str, Any]) -> Dict[str, Any]:
        to = parameters.get("recipient", "unknown@example.com")
        subject = parameters.get("subject", "(no subject)")
        logger.info(f"[MockEmailTool] Simulating email send to {to}")
        return {
            "status": "success",
            "message": f"Simulated email sent to {to}",
            "subject": subject,
        }


class MockFileTool:
    @staticmethod
    def read(parameters: Dict[str, Any]) -> Dict[str, Any]:
        path = parameters.get("path", "unknown_path")
        logger.info(f"[MockFileTool] Simulating file read: {path}")
        return {
            "status": "success",
            "message": f"Simulated read of '{path}'",
            "bytes_read": random.randint(100, 5000),
        }


class ToolExecutor:
    """Dispatches an allowed action to the correct mock tool."""

    def execute(self, action_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if action_type == "database_delete":
            return MockDatabaseTool.delete(parameters)
        if action_type == "database_read":
            return MockDatabaseTool.read(parameters)
        if action_type == "send_email":
            return MockEmailTool.send(parameters)
        if action_type == "file_read":
            return MockFileTool.read(parameters)
        raise ValueError(f"No tool registered for action_type: {action_type}")
