import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.modules.orchestrator import Orchestrator
from app.modules.context_manager import DatabaseManager, RefactorHistory
from app.utils.types import Role

async def verify_performance_tracking():
    print("Starting E2E verification for performance tracking...")
    
    # 1. Mock dependencies
    agent_service = MagicMock()
    agent_service.swap = AsyncMock()
    agent_service.generate = AsyncMock()
    agent_service.unload = AsyncMock()
    
    # Mock model responses
    mock_response = {
        "choices": [{"message": {"content": "<plan>Test plan</plan><instructions>Test instructions</instructions><code >Test code</code><insights>Test insights</insights>"}}]
    }
    agent_service.generate.return_value = mock_response
    
    validator = MagicMock()
    validator.check_syntax.return_value = {"is_valid": True}
    validator.check_complexity.return_value = {"complexity_score": 5}
    
    db = DatabaseManager()
    
    client = MagicMock()
    client.id = str(uuid.uuid4())
    client.send_status = AsyncMock()
    client.send_result = AsyncMock()
    
    # 2. Initialize Orchestrator
    orchestrator = Orchestrator(agent_service, validator, db)
    # Mock model config to avoid file IO if possible or use real one
    orchestrator.model_config = {
        "planner": {"filename": "p", "layers": 0, "context_size": 1, "temperature": 0.1, "max_tokens": 1, "sysprompt": "s"},
        "generator": {"filename": "g", "layers": 0, "context_size": 1, "temperature": 0.1, "max_tokens": 1, "sysprompt": "s"},
        "judge": {"filename": "j", "layers": 0, "context_size": 1, "temperature": 0.1, "max_tokens": 1, "sysprompt_error_interpreter": "s", "sysprompt_insights": "s"}
    }

    # 3. Execute orchestration
    await orchestrator.execute_orchestration(client, "public class Test {}", "refactor this")

    # 4. Verify client received performance metrics
    print("Verifying client.send_result call...")
    assert client.send_result.called
    args, kwargs = client.send_result.call_args
    performance = kwargs.get("performance_metrics")
    assert performance is not None
    assert "avg_gpu_utilization" in performance
    assert "avg_gpu_memory" in performance
    assert "avg_gpu_memory_used" in performance
    assert "inference_time" in performance
    print(f"Metrics received by client: {performance}")

    # Manually trigger DB completion because client is a mock
    db.complete_session(
        id=client.id,
        refactored_code="Test code",
        insights="Test insights",
        complexity=5,
        performance_metrics=performance
    )

    # 5. Verify database persistence
    print("Verifying database persistence...")
    record = RefactorHistory.get(RefactorHistory.id == client.id)
    assert record.status == "Completed"
    assert record.avg_gpu_utilization == performance["avg_gpu_utilization"]
    assert record.avg_gpu_memory == performance["avg_gpu_memory"]
    assert record.avg_gpu_memory_used == performance["avg_gpu_memory_used"]
    assert record.inference_time == performance["inference_time"]
    print(f"Database record updated successfully with metrics: {record.avg_gpu_utilization}, {record.avg_gpu_memory}, {record.inference_time}")

    print("Verification SUCCESSFUL!")

if __name__ == "__main__":
    asyncio.run(verify_performance_tracking())
