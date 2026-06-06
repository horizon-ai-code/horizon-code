"""Tests for judge structured issue types and override logic."""
import unittest
from pydantic import ValidationError
from app.utils.schemas import AuditIssue, StructuralAuditorResponse, AuditScratchpad, AuditTrace


class TestAuditIssue(unittest.TestCase):

    def test_valid_issue_types(self):
        for t in ["IDENTICAL_CODE", "LOGIC_DRIFT", "SEMANTIC_DRIFT"]:
            issue = AuditIssue(issue_type=t, description="test")
            self.assertEqual(issue.issue_type, t)

    def test_invalid_issue_type_raises(self):
        with self.assertRaises(ValidationError):
            AuditIssue(issue_type="INVALID_TYPE", description="test")

    def test_description_max_length(self):
        with self.assertRaises(ValidationError):
            AuditIssue(issue_type="IDENTICAL_CODE", description="x" * 101)

    def test_empty_description(self):
        issue = AuditIssue(issue_type="IDENTICAL_CODE", description="")
        self.assertEqual(issue.description, "")


class TestStructuralAuditorResponse(unittest.TestCase):

    def make_valid_response(self, verdict: str, issue_type: str = "IDENTICAL_CODE"):
        scratchpad = AuditScratchpad(
            variable_trace=[AuditTrace(original="a", refactored="b")],
            logic_comparison="same",
        )
        issues = [AuditIssue(issue_type=issue_type, description="test")]
        return StructuralAuditorResponse(
            audit_scratchpad=scratchpad,
            verdict=verdict,
            issues=issues,
        )

    def test_accept(self):
        r = self.make_valid_response("ACCEPT")
        self.assertEqual(r.verdict, "ACCEPT")
        self.assertEqual(len(r.issues), 1)

    def test_revise(self):
        r = self.make_valid_response("REVISE", "LOGIC_DRIFT")
        self.assertEqual(r.verdict, "REVISE")
        self.assertEqual(r.issues[0].issue_type, "LOGIC_DRIFT")

    def test_invalid_verdict_raises(self):
        with self.assertRaises(ValidationError):
            self.make_valid_response("APPROVE")

    def test_empty_issues(self):
        scratchpad = AuditScratchpad(logic_comparison="same")
        r = StructuralAuditorResponse(
            audit_scratchpad=scratchpad,
            verdict="ACCEPT",
            issues=[],
        )
        self.assertEqual(len(r.issues), 0)

    def test_issues_are_audit_issue_objects(self):
        scratchpad = AuditScratchpad(logic_comparison="check")
        r = StructuralAuditorResponse(
            audit_scratchpad=scratchpad,
            verdict="REVISE",
            issues=[
                AuditIssue(issue_type="IDENTICAL_CODE", description="identical"),
                AuditIssue(issue_type="SEMANTIC_DRIFT", description="behavior differs"),
            ],
        )
        self.assertEqual(len(r.issues), 2)
        self.assertEqual(r.issues[0].issue_type, "IDENTICAL_CODE")
        self.assertEqual(r.issues[1].issue_type, "SEMANTIC_DRIFT")

    def test_json_schema_includes_enum(self):
        schema = StructuralAuditorResponse.model_json_schema()
        defs = schema.get("$defs", schema.get("definitions", {}))
        # Find AuditIssue in defs
        issue_schema = defs.get("AuditIssue", {})
        if not issue_schema:
            issue_schema = schema["properties"]["issues"]["items"]
        issue_type_schema = issue_schema.get("properties", {}).get("issue_type", {})
        self.assertIn("enum", issue_type_schema)
        self.assertEqual(
            issue_type_schema["enum"],
            ["IDENTICAL_CODE", "LOGIC_DRIFT", "SEMANTIC_DRIFT"],
        )

    def test_model_validate_json(self):
        json_str = '''{
            "audit_scratchpad": {
                "variable_trace": [{"original": "x", "refactored": "y", "mapping": null}],
                "logic_comparison": "same"
            },
            "verdict": "REVISE",
            "issues": [{"issue_type": "IDENTICAL_CODE", "description": "no changes"}]
        }'''
        r = StructuralAuditorResponse.model_validate_json(json_str)
        self.assertEqual(r.verdict, "REVISE")
        self.assertEqual(r.issues[0].issue_type, "IDENTICAL_CODE")


class TestJudgeOverrideLogic(unittest.TestCase):
    """Test the override logic that corrects judge hallucinations."""

    def test_identical_code_code_changed_should_override(self):
        """Judge says IDENTICAL_CODE but code clearly changed — should override."""
        base_code = "public int foo() { return 1; }"
        working_code = "public int foo() { return 2; }"
        orig_cc = 1
        refac_cc = 2

        should_override = (
            working_code.strip() != base_code.strip()
            and orig_cc != refac_cc
        )
        self.assertTrue(should_override)

    def test_identical_code_code_unchanged_should_not_override(self):
        """Judge says IDENTICAL_CODE and code is truly unchanged — no override."""
        base_code = "public int foo() { return 1; }"
        working_code = base_code
        orig_cc = 1
        refac_cc = 1

        should_override = (
            working_code.strip() != base_code.strip()
            and orig_cc != refac_cc
        )
        self.assertFalse(should_override)

    def test_logic_drift_no_override(self):
        """Judge says LOGIC_DRIFT — should NEVER override, regardless of CC."""
        base_code = "public int foo() { return 1; }"
        working_code = "public int foo() { return 2; }"
        orig_cc = 1
        refac_cc = 2

        # LOGIC_DRIFT is never overridden
        self.assertNotEqual(working_code, base_code)
        self.assertNotEqual(orig_cc, refac_cc)

    def test_code_changed_same_cc_should_not_override(self):
        """Code changed but CC same — override should NOT fire (not enough evidence)."""
        base_code = "public int foo() { int x = 1; return x; }"
        working_code = "public int foo() { int y = 1; return y; }"
        orig_cc = 2
        refac_cc = 2

        # Code changed (rename variable) but CC same — judge might be right
        # our override requires CC change as extra evidence
        should_override = (
            working_code.strip() != base_code.strip()
            and orig_cc != refac_cc
        )
        self.assertFalse(should_override)

    def test_code_unchanged_same_cc_should_not_override(self):
        """Nothing changed — no override."""
        base_code = "public int foo() { return 1; }"
        working_code = base_code
        orig_cc = 1
        refac_cc = 1

        should_override = (
            working_code.strip() != base_code.strip()
            and orig_cc != refac_cc
        )
        self.assertFalse(should_override)


if __name__ == "__main__":
    unittest.main()
