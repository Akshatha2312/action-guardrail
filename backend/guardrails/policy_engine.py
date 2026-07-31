"""Generic policy engine.

Policies are declarative YAML rules with a single condition each. New
operators or rules can be added without touching any other part of the
application - this module is the only place that needs to change.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

from backend.config.settings import POLICY_PATH
from backend.config.logging_config import logger


@dataclass
class MatchedRule:
    id: str
    description: str
    outcome: str


class PolicyEngine:
    def __init__(self, policy_path: str = POLICY_PATH):
        self.policy_path = policy_path
        self.internal_domains: List[str] = []
        self.rules: List[Dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        """(Re)load policies from the YAML file. Called on startup and can be
        called again at runtime without restarting the service."""
        with open(self.policy_path, "r") as f:
            config = yaml.safe_load(f) or {}
        self.internal_domains = [d.lower() for d in config.get("internal_domains", [])]
        self.rules = config.get("policies", [])
        logger.info(f"Loaded {len(self.rules)} policies from {self.policy_path}")

    # ------------------------------------------------------------------
    # Operators
    # ------------------------------------------------------------------
    def _apply_operator(self, operator: str, actual: Any, expected: Any) -> bool:
        if actual is None:
            return False

        if operator == "greater_than":
            return float(actual) > float(expected)
        if operator == "greater_than_or_equal":
            return float(actual) >= float(expected)
        if operator == "less_than":
            return float(actual) < float(expected)
        if operator == "less_than_or_equal":
            return float(actual) <= float(expected)
        if operator == "equals":
            return str(actual).lower() == str(expected).lower()
        if operator == "not_equals":
            return str(actual).lower() != str(expected).lower()
        if operator == "contains":
            return str(expected).lower() in str(actual).lower()
        if operator == "not_contains":
            return str(expected).lower() not in str(actual).lower()
        if operator == "external_domain":
            domain = str(actual).lower()
            return domain not in self.internal_domains
        if operator == "internal_domain":
            domain = str(actual).lower()
            return domain in self.internal_domains

        raise ValueError(f"Unknown operator: {operator}")

    def _field_value(self, field: str, parameters: Dict[str, Any]) -> Any:
        return parameters.get(field)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(self, action_type: str, parameters: Dict[str, Any]) -> List[MatchedRule]:
        """Return every rule that matches this action. Caller decides priority."""
        matches: List[MatchedRule] = []
        for rule in self.rules:
            if rule.get("action_type") != action_type:
                continue
            condition = rule.get("condition", {})
            field = condition.get("field")
            operator = condition.get("operator")
            expected = condition.get("value")

            actual = self._field_value(field, parameters)
            try:
                if self._apply_operator(operator, actual, expected):
                    matches.append(
                        MatchedRule(
                            id=rule["id"],
                            description=rule.get("description", ""),
                            outcome=rule["outcome"],
                        )
                    )
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping rule '{rule.get('id')}' due to evaluation error: {e}")
                continue
        return matches

    # ------------------------------------------------------------------
    # Priority resolution
    # ------------------------------------------------------------------
    OUTCOME_PRIORITY = {"block": 0, "require_hitl": 1, "log_and_allow": 2}

    def resolve(self, matches: List[MatchedRule]) -> Optional[MatchedRule]:
        """Fail-closed priority: BLOCK > REQUIRE_HITL > LOG_AND_ALLOW.

        If several rules match with the same outcome, the first one defined
        in the YAML file (list order) wins, giving policy authors explicit
        control via ordering.
        """
        if not matches:
            return None
        return sorted(matches, key=lambda m: self.OUTCOME_PRIORITY.get(m.outcome, 99))[0]
