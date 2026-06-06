import unittest
import json
from app.utils.response_parser import ResponseParser
from app.utils.schemas import IntentPacket
from app.utils.types import RefactorCategory, RefactorIntent, StructureUnit

class TestResponseParser(unittest.TestCase):
    def test_extract_xml_basic(self):
        text = "Thinking... <plan>Goal</plan> noise"
        self.assertEqual(ResponseParser.extract_xml(text, "plan"), "Goal")

    def test_extract_xml_with_thinking_block(self):
        text = "<think>hide this</think> <code>int x = 1;</code>"
        self.assertEqual(ResponseParser.extract_xml(text, "code"), "int x = 1;")

    def test_extract_xml_java_validation(self):
        # Invalid java snippet (no { or ;)
        text = "<code>invalid code</code>"
        self.assertIsNone(ResponseParser.extract_xml(text, "code"))
        
        # Valid java snippet
        text = "<code>int x = 1;</code>"
        self.assertEqual(ResponseParser.extract_xml(text, "code"), "int x = 1;")

    def test_extract_json_pydantic(self):
        data = {
            "refactor_category": "CONTROL_FLOW",
            "specific_intent": "FLATTEN_CONDITIONAL",
            "scope_anchor": {
                "class": "MyClass",
                "unit_type": "CLASS_UNIT"
            }
        }
        text = f"Json here: ```json\n{json.dumps(data)}\n```"
        result = ResponseParser.extract_json(text, IntentPacket)
        self.assertEqual(result.refactor_category, RefactorCategory.CONTROL_FLOW)
        self.assertEqual(result.scope_anchor.target_class, "MyClass")

    def test_extract_json_fallback_cleaning(self):
        # JSON with a trailing comma
        text = '{"refactor_category": "CONTROL_FLOW", "specific_intent": "SPLIT_LOOP", "scope_anchor": {"class": "A", "unit_type": "METHOD_UNIT"}, }'
        result = ResponseParser.extract_json(text, IntentPacket)
        self.assertEqual(result.specific_intent, RefactorIntent.SPLIT_LOOP)

    def test_extract_json_python_keywords(self):
        # JSON containing None instead of null
        text = '{"refactor_category": "CONTROL_FLOW", "specific_intent": "REMOVE_CONTROL_FLAG", "scope_anchor": {"class": "A", "member": None, "unit_type": "METHOD_UNIT"}}'
        result = ResponseParser.extract_json(text, IntentPacket)
        self.assertIsNone(result.scope_anchor.member)

        # JSON containing True/False
        # (Assuming IntentPacket doesn't have booleans, using a mock model check if needed or just validating it doesn't crash)
        text = '{"refactor_category": "CONTROL_FLOW", "specific_intent": "REMOVE_CONTROL_FLAG", "scope_anchor": {"class": "A", "is_valid": True, "unit_type": "METHOD_UNIT"}}'
        # If the model ignores extra fields, this should pass after cleaning
        result = ResponseParser.extract_json(text, IntentPacket)
        self.assertEqual(result.specific_intent, RefactorIntent.REMOVE_CONTROL_FLAG)

if __name__ == '__main__':
    unittest.main()
