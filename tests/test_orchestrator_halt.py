import unittest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.orchestrator import Orchestrator, OrchestrationState
from app.utils.types import Role

class TestOrchestratorHalt(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent_service = MagicMock()
        self.agent_service.swap = AsyncMock()
        self.agent_service.generate = AsyncMock()
        self.agent_service.unload = AsyncMock()
        self.agent_service.clear_context = AsyncMock()
        
        self.validator = MagicMock()
        self.db = MagicMock()
        
        self.client = MagicMock()
        self.client.id = "test-session-id"
        self.client.send_status = AsyncMock()
        self.client.send_result = AsyncMock()
        
        # Mocking model_config and prompts loading
        self.mock_config = {
            "planner": {"filename": "p", "name": "p"},
            "generator": {"filename": "g", "name": "g"},
            "judge": {"filename": "j", "name": "j"}
        }
        self.mock_prompts = {
            "planner": {"classifier": "c", "architect": "a"},
            "generator": {"coder": "co"},
            "judge": {"auditor": "au", "insights": "i"}
        }

    @patch("builtins.open")
    @patch("yaml.safe_load")
    async def test_execute_orchestration_handles_cancellation(self, mock_yaml, mock_open):
        mock_yaml.side_effect = [self.mock_config, self.mock_prompts]
        orchestrator = Orchestrator(self.agent_service, self.validator, self.db)
        
        # Force asyncio.CancelledError during the first baseline phase notification
        # (Or any point early in the execution)
        self.validator.get_complexity.side_effect = asyncio.CancelledError()
        
        with self.assertRaises(asyncio.CancelledError):
            await orchestrator.execute_orchestration(self.client, "public class Test {}", "Refactor.")
            
        self.db.mark_as_halted.assert_called_once_with(self.client.id)
        self.agent_service.unload.assert_called_once()

    @patch("builtins.open")
    @patch("yaml.safe_load")
    async def test_execute_orchestration_unloads_on_error(self, mock_yaml, mock_open):
        mock_yaml.side_effect = [self.mock_config, self.mock_prompts]
        orchestrator = Orchestrator(self.agent_service, self.validator, self.db)
        
        self.validator.get_complexity.side_effect = ValueError("Fatal Error")
        
        with self.assertRaises(ValueError):
            await orchestrator.execute_orchestration(self.client, "public class Test {}", "Refactor.")
            
        self.agent_service.unload.assert_called_once()

if __name__ == "__main__":
    unittest.main()
