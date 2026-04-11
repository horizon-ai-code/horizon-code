# GPU Tracking and Inference Time Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real-time GPU utilization/memory tracking and inference time monitoring during orchestration, reporting results to the frontend and persisting them in the database.

**Architecture:** A `PerformanceTracker` utility will poll GPU stats in a background task using `pynvml`. The `Orchestrator` will manage the tracker's lifecycle and pass the final metrics to the `ConnectionManager` and `DatabaseManager`.

**Tech Stack:** Python, `nvidia-ml-py` (pynvml), Peewee ORM, FastAPI.

---

### Task 1: Performance Tracker Utility

**Files:**
- Create: `app/utils/performance.py`
- Test: `tests/test_performance.py`

- [ ] **Step 1: Write initial tests for PerformanceTracker**
```python
import pytest
import asyncio
from app.utils.performance import PerformanceTracker

@pytest.mark.asyncio
async def test_performance_tracker_collects_metrics():
    tracker = PerformanceTracker(interval=0.1)
    await tracker.start_tracking()
    await asyncio.sleep(0.3)
    await tracker.stop_tracking()
    metrics = tracker.get_metrics()
    
    assert "avg_gpu_utilization" in metrics
    assert "avg_gpu_memory" in metrics
    assert "inference_time" in metrics
    assert metrics["inference_time"] >= 0.3
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_performance.py`
Expected: `ModuleNotFoundError: No module named 'app.utils.performance'`

- [ ] **Step 3: Implement PerformanceTracker**
```python
import asyncio
import time
import pynvml
from typing import List, Dict, Optional

class PerformanceTracker:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._gpu_utilizations: List[float] = []
        self._gpu_memory_usage: List[float] = []
        self._start_time: float = 0
        self._total_inference_time: float = 0
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        self._has_gpu = False

    async def start_tracking(self):
        self._is_running = True
        self._gpu_utilizations = []
        self._gpu_memory_usage = []
        self._start_time = time.perf_counter()
        
        try:
            pynvml.nvmlInit()
            self._has_gpu = True
            self._task = asyncio.create_task(self._poll_gpu())
        except Exception as e:
            print(f"[PerformanceTracker] NVML initialization failed: {e}")
            self._has_gpu = False

    async def stop_tracking(self):
        self._is_running = False
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._total_inference_time = time.perf_counter() - self._start_time
        if self._has_gpu:
            try:
                pynvml.nvmlShutdown()
            except:
                pass

    async def _poll_gpu(self):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            while self._is_running:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                self._gpu_utilizations.append(float(util.gpu))
                self._gpu_memory_usage.append(float(mem.used) / float(mem.total) * 100.0)
                
                await asyncio.sleep(self.interval)
        except Exception as e:
            print(f"[PerformanceTracker] Polling error: {e}")

    def get_metrics(self) -> Dict[str, float]:
        avg_util = sum(self._gpu_utilizations) / len(self._gpu_utilizations) if self._gpu_utilizations else 0
        avg_mem = sum(self._gpu_memory_usage) / len(self._gpu_memory_usage) if self._gpu_memory_usage else 0
        return {
            "avg_gpu_utilization": round(avg_util, 2),
            "avg_gpu_memory": round(avg_mem, 2),
            "inference_time": round(self._total_inference_time, 2)
        }
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_performance.py`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/utils/performance.py tests/test_performance.py
git commit -m "feat: implement PerformanceTracker utility"
```

### Task 2: Database Schema and Logic Updates

**Files:**
- Modify: `app/modules/context_manager.py`

- [ ] **Step 1: Add performance fields to RefactorHistory**
Modify `class RefactorHistory(peewee.Model)`:
```python
    avg_gpu_utilization = peewee.FloatField(null=True)
    avg_gpu_memory = peewee.FloatField(null=True)
    inference_time = peewee.FloatField(null=True)
```

- [ ] **Step 2: Update complete_session signature and logic**
```python
    def complete_session(
        self,
        id: str,
        refactored_code: str,
        insights: str,
        complexity: Optional[int],
        performance_metrics: Dict[str, float], # New
    ) -> None:
        """Updates an existing session record with final results."""
        with db.atomic():
            query = RefactorHistory.update(
                status="Completed",
                refactored_code=refactored_code,
                insights=insights,
                complexity=complexity,
                avg_gpu_utilization=performance_metrics.get("avg_gpu_utilization"),
                avg_gpu_memory=performance_metrics.get("avg_gpu_memory"),
                inference_time=performance_metrics.get("inference_time"),
            ).where(RefactorHistory.id == id)
            query.execute()
```

- [ ] **Step 3: Run existing database tests to find regressions**
Run: `pytest tests/test_context_manager.py`

- [ ] **Step 4: Fix any test regressions due to signature change**
(Pass `{}` as the final argument in any test calling `complete_session`)

- [ ] **Step 5: Commit**
```bash
git add app/modules/context_manager.py
git commit -m "feat: add performance fields to database schema"
```

### Task 3: Connection Manager and Pydantic Model Updates

**Files:**
- Modify: `app/modules/connection_manager.py`
- Modify: `app/utils/schemas.py`

- [ ] **Step 1: Update ClientConnection.send_result**
```python
    async def send_result(
        self,
        final_code: str,
        insights: str,
        complexity: Optional[int],
        performance_metrics: Dict[str, float], # New
    ):
        # 1. Update the existing session record with final results
        self.db.complete_session(
            id=self.id,
            refactored_code=final_code,
            insights=insights,
            complexity=complexity,
            performance_metrics=performance_metrics, # New
        )

        # 2. Send the final result payload to the frontend
        message: dict = {
            "type": "result",
            "id": self.id,
            "code": final_code,
            "complexity": complexity,
            "insights": insights,
            "performance": performance_metrics # New
        }
        await self.websocket.send_json(message)
```

- [ ] **Step 2: Update HistoryDetail Pydantic model**
In `app/utils/schemas.py`:
```python
class HistoryDetail(BaseModel):
    id: UUID4
    user_instruction: str
    original_code: str
    refactored_code: Optional[str] = None
    insights: Optional[str] = None
    complexity: Optional[int] = None
    avg_gpu_utilization: Optional[float] = None # New
    avg_gpu_memory: Optional[float] = None # New
    inference_time: Optional[float] = None # New
    created_at: datetime
    logs: List[LogEntry]
```

- [ ] **Step 3: Commit**
```bash
git add app/modules/connection_manager.py app/utils/schemas.py
git commit -m "feat: update connection manager and schemas for performance metrics"
```

### Task 4: Orchestrator Integration

**Files:**
- Modify: `app/modules/orchestrator.py`

- [ ] **Step 1: Import PerformanceTracker and integrate lifecycle**
At the top of `app/modules/orchestrator.py`:
```python
from app.utils.performance import PerformanceTracker
```

In `execute_orchestration` method:
```python
    async def execute_orchestration(
        self, client: ClientConnection, user_code: str, user_instruction: str
    ) -> None:
        tracker = PerformanceTracker() # Init tracker
        await tracker.start_tracking() # Start tracking
        try:
            # ... existing orchestration code ...

            # Before final send_result:
            await tracker.stop_tracking()
            metrics = tracker.get_metrics()

            await client.send_result(
                final_code=current_code,
                insights=insights["insights"],
                complexity=complexity_score,
                performance_metrics=metrics # Pass metrics
            )
        except asyncio.CancelledError:
            await tracker.stop_tracking() # Ensure stopped on halt
            self.db.mark_as_halted(client.id)
            await self._notify(client, Role.System, "Process halted.")
            raise
        except Exception as e:
            await tracker.stop_tracking() # Ensure stopped on error
            raise e
        finally:
            await self.agent_service.unload()
```

- [ ] **Step 2: Commit**
```bash
git add app/modules/orchestrator.py
git commit -m "feat: integrate performance tracking into orchestration loop"
```

### Task 5: End-to-End Verification

- [ ] **Step 1: Create verification script**
Create `tests/verify_performance_tracking.py` (minimal orchestration mock).

- [ ] **Step 2: Run verification script**
Run: `python tests/verify_performance_tracking.py`

- [ ] **Step 3: Commit**
```bash
git add tests/verify_performance_tracking.py
git commit -m "test: add e2e verification for performance tracking"
```
