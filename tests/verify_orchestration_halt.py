import asyncio
import json
import unittest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.modules.context_manager import DatabaseManager, RefactorHistory, db
from app.utils.types import Role

# Use a test database
TEST_DB_PATH = "test_history.db"

class VerifyOrchestrationHalt(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Point peewee to a test database
        # We need to re-initialize the database connection for testing
        db.init(TEST_DB_PATH, pragmas={"journal_mode": "wal"})
        db.connect(reuse_if_open=True)
        db.create_tables([RefactorHistory], safe=True)
        self.db_manager = DatabaseManager()

    async def asyncTearDown(self):
        db.close()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        if os.path.exists(f"{TEST_DB_PATH}-shm"):
            os.remove(f"{TEST_DB_PATH}-shm")
        if os.path.exists(f"{TEST_DB_PATH}-wal"):
            os.remove(f"{TEST_DB_PATH}-wal")

    async def test_full_halt_flow_and_lock_release(self):
        """
        Verifies:
        1. Halt signal is handled.
        2. DB status is updated to 'Halted'.
        3. orchestration_lock is released.
        4. A new orchestration can start immediately after.
        """
        # 1. Mock AgentService to be slow but interruptible
        # We patch at the agent_service level used by the orchestrator in app.main
        from app.main import orchestrator
        
        # We'll use an Event to coordinate between the mock and the test
        task_a_started = asyncio.Event()
        task_a_can_continue = asyncio.Event()

        async def slow_swap(*args, **kwargs):
            task_a_started.set()
            try:
                # Wait for the test to tell us to continue (which it won't, it will halt us)
                await task_a_can_continue.wait()
            except asyncio.CancelledError:
                raise

        # Patch agent_service.swap
        print("Patching agent_service methods...")
        with patch.object(orchestrator.agent_service, 'swap', side_effect=slow_swap):
            # Patch agent_service.unload to avoid real model unloading issues
            with patch.object(orchestrator.agent_service, 'unload', new_callable=AsyncMock):
                
                print("Starting TestClient...")
                client = TestClient(app)
                with client.websocket_connect("/ws") as websocket:
                    print("WebSocket connected.")
                    # --- TASK A ---
                    # 2. Start Task A
                    print("Sending RefactorRequest A...")
                    websocket.send_json({
                        "code": "public class TaskA {}",
                        "user_instruction": "Refactor Task A."
                    })
                    
                    # 3. Wait for Task A to start (it will call swap and set the event)
                    # We also wait for the connection_id message
                    print("Waiting for connection_id...")
                    msg = websocket.receive_json()
                    self.assertEqual(msg.get("type"), "connection_id")
                    session_a_id = msg.get("id")
                    print(f"Received connection_id: {session_a_id}")
                    
                    # Wait for status update indicating it started
                    # (Planner generating plan...)
                    print("Waiting for Planner status...")
                    msg = websocket.receive_json()
                    self.assertEqual(msg.get("role"), Role.Planner)
                    print(f"Received Planner status: {msg.get('content')}")
                    
                    # 4. Halt Task A
                    print("Sending HaltRequest A...")
                    websocket.send_json({"type": "halt"})
                    
                    # 5. Verify halt notification received
                    print("Waiting for halt notification...")
                    msg = websocket.receive_json()
                    print(f"Received message after halt: {msg}")
                    # It might be "Process halted." from orchestrator or "Orchestration halted by user." from main.py
                    # Based on main.py, it sends "Orchestration halted by user." upon CancelledError
                    self.assertIn("halted", msg.get("content", "").lower())
                    
                    # 6. Verify DB status for Session A
                    # Wait a tiny bit for the async DB update to complete
                    print("Checking DB for Session A status...")
                    await asyncio.sleep(0.5)
                    session_a = RefactorHistory.get(RefactorHistory.id == session_a_id)
                    self.assertEqual(session_a.status, "Halted")
                    print(f"Verified: Session {session_a_id} status is 'Halted'")

                    # --- TASK B ---
                    # 7. Start Task B (proving the lock was released)
                    print("Preparing Task B...")
                    # We need to change the mock behavior for Task B to let it finish
                    task_b_started = asyncio.Event()
                    async def fast_swap(*args, **kwargs):
                        print("Task B: fast_swap called")
                        task_b_started.set()
                        return None
                    
                    with patch.object(orchestrator.agent_service, 'swap', side_effect=fast_swap):
                        # Mock other methods needed for completion
                        with patch.object(orchestrator, 'generate_plan_and_instruction', new_callable=AsyncMock) as mock_plan:
                            mock_plan.return_value = {"plan": "Plan B", "instructions": "Instruct B"}
                            with patch.object(orchestrator, 'generate_refactored_code', new_callable=AsyncMock) as mock_gen:
                                mock_gen.return_value = {"code": "public class TaskBRefactored {}"}
                                with patch.object(orchestrator, 'generate_insights', new_callable=AsyncMock) as mock_insights:
                                    mock_insights.return_value = {"insights": "Insights B"}
                                    
                                    print("Sending RefactorRequest B...")
                                    websocket.send_json({
                                        "code": "public class TaskB {}",
                                        "user_instruction": "Refactor Task B."
                                    })
                                    
                                    # Wait for connection_id for Task B
                                    print("Waiting for connection_id B...")
                                    msg = websocket.receive_json()
                                    session_b_id = msg.get("id")
                                    print(f"Received connection_id B: {session_b_id}")
                                    self.assertNotEqual(session_a_id, session_b_id)
                                    
                                    # Wait for messages from Task B
                                    # If Task B starts, the lock was released.
                                    print("Waiting for Task B progress...")
                                    b_started = False
                                    for _ in range(10): # Receive up to 10 messages
                                        msg = websocket.receive_json()
                                        print(f"Received message from B: {msg}")
                                        if msg.get("type") == "result" and msg.get("id") == session_b_id:
                                            b_started = True
                                            break
                                        if msg.get("role") == Role.Planner:
                                            b_started = True
                                    
                                    self.assertTrue(b_started, "Task B failed to start after Task A was halted")
                                    print(f"Verified: Task B started successfully after Task A halt (Lock released)")

                    # 8. Verify orchestration_lock is not locked
                    from app.main import orchestration_lock
                    self.assertFalse(orchestration_lock.locked())
                    print("Verified: orchestration_lock is released")

if __name__ == "__main__":
    unittest.main()
