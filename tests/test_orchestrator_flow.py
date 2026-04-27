import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.orchestrator import Orchestrator
from app.modules.agent_service import AgentService
from app.modules.validator import Validator
from app.modules.context_manager import DatabaseManager
from app.utils.types import Role, ExitStatus

class MockClient:
    def __init__(self):
        self.id = "test-session"
        self.statuses = []
        self.results = None

    async def send_status(self, role, content):
        self.statuses.append((role, content))

    async def send_result(self, **kwargs):
        self.results = kwargs

class TestOrchestratorFlow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent_service = MagicMock(spec=AgentService)
        self.agent_service.generate = AsyncMock()
        self.agent_service.swap = AsyncMock()
        self.agent_service.unload = AsyncMock()
        self.agent_service.clear_context = AsyncMock()
        
        self.validator = Validator()
        self.db = MagicMock(spec=DatabaseManager)
        
        self.mock_config = {
            "planner": {"name": "p", "filename": "p"},
            "generator": {"name": "g", "filename": "g"},
            "judge": {"name": "j", "filename": "j"}
        }
        self.mock_prompts = {
            "planner": {"classifier": "c", "architect": "a"},
            "generator": {"coder": "co"},
            "judge": {"auditor": "au", "insights": "i"}
        }

    @patch("builtins.open")
    @patch("yaml.safe_load")
    async def test_full_success_flow(self, mock_yaml, mock_open):
        mock_yaml.side_effect = [self.mock_config, self.mock_prompts]
        orch = Orchestrator(self.agent_service, self.validator, self.db)
        
        # Define LLM response sequence
        responses = [
            # Ph2: Classifier
            json.dumps({"classification_scratchpad": "t", "intent_packet": {"refactor_category": "CONTROL_FLOW", "specific_intent": "FLATTEN_CONDITIONAL", "scope_anchor": {"class": "A", "member": "m", "unit_type": "METHOD_UNIT"}}}),
            # Ph2: Architect
            json.dumps({"architect_scratchpad": "t", "ast_modification_plan": {"target_class": "A", "ast_mutations": []}}),
            # Ph3: Coder
            "<code>public class A { void m() { } }</code>",
            # Ph5: Auditor
            json.dumps({"audit_scratchpad": {"variable_trace": [], "logic_comparison": "ok"}, "verdict": "ACCEPT", "issues": []}),
            # Ph6: Insights
            "<insights>Refactor look good.</insights>"
        ]
        
        async def mock_gen(messages, **kwargs):
            content = responses.pop(0)
            return {"choices": [{"message": {"content": content}}]}
            
        self.agent_service.generate.side_effect = mock_gen
        
        client = MockClient()
        user_code = "public class A { void m() { if(a) { if(b) {} } } }"
        user_instruction = "Flatten it."
        
        await orch.execute_orchestration(client, user_code, user_instruction)
        
        self.assertEqual(client.results["insights"], "Refactor look good.")
        self.db.complete_session.assert_called_once()
        # Verify status transitions
        status_msgs = [s[1] for s in client.statuses]
        self.assertTrue(any("Ph1" in m for m in status_msgs))
        self.assertTrue(any("Ph2" in m for m in status_msgs))
        self.assertTrue(any("Ph3" in m for m in status_msgs))
        self.assertTrue(any("Ph4" in m for m in status_msgs))
        self.assertTrue(any("Ph5" in m for m in status_msgs))
        self.assertTrue(any("Ph6" in m for m in status_msgs))

if __name__ == '__main__':
    unittest.main()
