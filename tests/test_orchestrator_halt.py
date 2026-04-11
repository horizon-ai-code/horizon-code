import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.orchestrator import Orchestrator
from app.utils.types import Role

class TestOrchestratorHalt(unittest.IsolatedAsyncioTestCase):
    async def test_execute_orchestration_handles_cancellation(self):
        # 1. Mock dependencies
        agent_service = MagicMock()
        agent_service.swap = AsyncMock()
        agent_service.generate = AsyncMock()
        agent_service.unload = AsyncMock()
        
        validator = MagicMock()
        db = MagicMock()
        
        client = MagicMock()
        client.id = "test-session-id"
        client.send_status = AsyncMock()
        client.send_result = AsyncMock()
        
        # 2. Setup Orchestrator with mocked config
        with patch("builtins.open", unittest.mock.mock_open(read_data='planner: {sysprompt: "...", temperature: 0, max_tokens: 100}\ngenerator: {sysprompt: "...", temperature: 0, max_tokens: 100}\njudge: {sysprompt_error_interpreter: "...", sysprompt_insights: "...", temperature: 0, max_tokens: 100}')):
            orchestrator = Orchestrator(agent_service, validator, db)
            
        # 3. Force asyncio.CancelledError during the first swap
        agent_service.swap.side_effect = asyncio.CancelledError()
        
        # 4. Execute orchestration and expect CancelledError to be raised
        with self.assertRaises(asyncio.CancelledError):
            await orchestrator.execute_orchestration(client, "public class Test {}", "Refactor this.")
            
        # 5. Verifications
        # Verify db.mark_as_halted was called with client.id
        db.mark_as_halted.assert_called_once_with(client.id)
        
        # Verify _notify was called (which calls db.log_status and client.send_status)
        # Specifically checking for "Process halted." notification
        db.log_status.assert_any_call(
            session_id=client.id,
            role=Role.System,
            status="Process halted.",
            content=None
        )
        client.send_status.assert_any_call(
            role=Role.System,
            content="Process halted."
        )
        
        # Verify agent_service.unload was called in finally block
        agent_service.unload.assert_called_once()

    async def test_execute_orchestration_unloads_on_error(self):
        # 1. Mock dependencies
        agent_service = MagicMock()
        agent_service.swap = AsyncMock()
        agent_service.unload = AsyncMock()
        
        validator = MagicMock()
        db = MagicMock()
        
        client = MagicMock()
        client.id = "test-session-id"
        
        # 2. Setup Orchestrator
        with patch("builtins.open", unittest.mock.mock_open(read_data='planner: {sysprompt: "...", temperature: 0, max_tokens: 100}\ngenerator: {sysprompt: "...", temperature: 0, max_tokens: 100}\njudge: {sysprompt_error_interpreter: "...", sysprompt_insights: "...", temperature: 0, max_tokens: 100}')):
            orchestrator = Orchestrator(agent_service, validator, db)
            
        # 3. Force a normal exception during the first swap
        agent_service.swap.side_effect = ValueError("Something went wrong")
        
        # 4. Execute orchestration and expect ValueError to be raised
        with self.assertRaises(ValueError):
            await orchestrator.execute_orchestration(client, "public class Test {}", "Refactor this.")
            
        # 5. Verify agent_service.unload was called in finally block
        agent_service.unload.assert_called_once()

if __name__ == "__main__":
    unittest.main()
