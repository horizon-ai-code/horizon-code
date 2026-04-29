import unittest
import json
from app.utils.formatters import format_agent_output

class TestFormatters(unittest.TestCase):
    def test_intent_packet_formatting(self):
        message = "Intent Classified"
        content = json.dumps({
            "refactor_category": "METHOD_MOVEMENT",
            "specific_intent": "EXTRACT_METHOD",
            "scope_anchor": {
                "unit_type": "CLASS_UNIT",
                "class": "Calculator"
            }
        })
        result = format_agent_output(message, content)
        self.assertIn("**Category:** `METHOD_MOVEMENT`", result)
        self.assertIn("**Intent:** `EXTRACT_METHOD`", result)
        self.assertIn("**Target Class:** `Calculator`", result)

    def test_ast_mutation_formatting(self):
        message = "Plan generated"
        content = json.dumps({
            "target_class": "AuthService",
            "ast_mutations": [
                {
                    "action": "ADD_METHOD",
                    "target": "validateToken",
                    "details": {
                        "logic_changes": ["Move JWT logic here", "Add null checks"]
                    }
                }
            ]
        })
        result = format_agent_output(message, content)
        self.assertIn("**Target Class:** `AuthService`", result)
        self.assertIn("- **ADD_METHOD** on `validateToken`", result)
        self.assertIn("- *Move JWT logic here*", result)

    def test_validation_finding_formatting(self):
        message = "Errors detected"
        content = json.dumps({
            "total_faults": 1,
            "is_recoverable": True,
            "findings": [
                {
                    "failure_tier": "TIER_1_SYNTAX",
                    "error_report": {
                        "message": "Missing semicolon",
                        "faulty_node": "System.out.println"
                    },
                    "recovery_hint": "Add ';' at the end of the line."
                }
            ]
        })
        result = format_agent_output(message, content)
        self.assertIn("**Total Faults:** 1", result)
        self.assertIn("**[TIER_1_SYNTAX]**", result)
        self.assertIn("> Missing semicolon", result)
        self.assertIn("*Hint:* Add ';' at the end of the line.", result)

    def test_validator_output_formatting(self):
        message = "Structural Checks Failed (1 issues)."
        content = json.dumps([
            {
                "failure_tier": "TIER_2_C_INTENT_MATH",
                "error_report": {
                    "message": "Nesting depth did not decrease.",
                    "faulty_node": "IfStatement"
                },
                "recovery_hint": "Check if the refactoring actually achieved the structural goal."
            }
        ])
        result = format_agent_output(message, content)
        self.assertIn("**Total Faults:** 1", result)
        self.assertIn("**[TIER_2_C_INTENT_MATH]**", result)
        self.assertIn("> Nesting depth did not decrease.", result)
        self.assertIn("- Node: `IfStatement`", result)
        self.assertIn("- *Hint:* Check if the refactoring actually achieved the structural goal.", result)
        self.assertNotIn("```json", result)

if __name__ == "__main__":
    unittest.main()
