"""Central configuration for the Action Guardrail platform.

All settings are loaded from environment variables (see .env.example),
with sane local-first defaults so the app runs out of the box.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Path to the SQLite audit database
DB_PATH = os.getenv("GUARDRAIL_DB_PATH", str(BASE_DIR / "guardrail.db"))

# Path to the YAML policy file
POLICY_PATH = os.getenv("GUARDRAIL_POLICY_PATH", str(BASE_DIR / "policies" / "policies.yaml"))

# Optional LLM integration - the core guardrail NEVER requires this.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# API host/port (used by run scripts / docs, not required for import)
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Parameter keys that should never be shown verbatim in the dashboard/API
SENSITIVE_PARAM_KEYS = {"password", "ssn", "api_key", "credit_card", "secret", "token"}
