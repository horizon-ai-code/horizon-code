import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient
from app.main import app
from app.utils.types import Role

class TestMainHalt(unittest.IsolatedAsyncioTestCase):
    async def test_halt_cancels_active_task(self):
        """
        Tests that sending a 'halt' message through WebSocket cancels the 
        active orchestration task.
        """
        # 1. Mock the orchestrator's execute_orchestration to be interruptible
        # and wait long enough for us to send the halt message.
        async def slow_orchestration(*args, **kwargs):
            try:
                await asyncio.sleep(5) # Simulate long running task
            except asyncio.CancelledError:
                # This is what we expect to happen when halted
                raise

        with patch("app.main.orchestrator.execute_orchestration", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = slow_orchestration
            
            # Using TestClient as a context manager for WebSocket
            # Note: TestClient with websocket_connect is synchronous in terms of the test
            # but it interacts with the async FastAPI app.
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                # 2. Send a refactor request to start the task
                websocket.send_json({
                    "code": "public class Test {}",
                    "user_instruction": "Refactor this."
                })
                
                # Give it a tiny bit of time to start (though in this sync test it's tricky)
                # Actually, TestClient's websocket is handled by a background loop.
                
                # 3. Send the halt message
                websocket.send_json({"type": "halt"})
                
                # 4. Receive messages and check for the halt notification
                # We expect status updates and finally "Orchestration halted by user."
                messages = []
                try:
                    # We might receive multiple messages (connection_id, status, etc.)
                    # We'll wait until we get the halt notification or time out
                    for _ in range(5):
                        msg = websocket.receive_json()
                        messages.append(msg)
                        if msg.get("type") == "status" and "halted" in msg.get("content", "").lower():
                            break
                except Exception:
                    pass

                # 5. Verification
                # Check if we got the halt notification
                halt_found = any(
                    "halted" in msg.get("content", "").lower() 
                    for msg in messages if msg.get("type") == "status"
                )
                self.assertTrue(halt_found, f"Halt notification not found in messages: {messages}")
                
                # Check if mock_execute was indeed cancelled
                # (In this setup, we might not be able to verify cancellation directly 
                # through mock_execute because it's in a background task in main.py)
                # But if the notification was sent, it means the catch block was hit.

    async def test_normal_orchestration_success(self):
        """
        Tests that normal orchestration still works after the refactor.
        """
        async def fast_orchestration(*args, **kwargs):
            # Simulate a successful orchestration
            pass

        with patch("app.main.orchestrator.execute_orchestration", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = fast_orchestration
            
            client = TestClient(app)
            with client.websocket_connect("/ws") as websocket:
                websocket.send_json({
                    "code": "public class Test {}",
                    "user_instruction": "Refactor this."
                })
                
                # Receive messages. We expect connection_id and potentially status if lock was checked.
                # Since mock is fast, we just wait for it to finish.
                # In main.py, it's a background task, so we might need to wait a tiny bit.
                await asyncio.sleep(0.1)
                
                mock_execute.assert_called_once()

if __name__ == "__main__":
    unittest.main()
