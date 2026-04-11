# Design Spec: GPU Tracking and Inference Time Monitoring

## 1. Problem Statement
The user wants to track GPU usage (utilization and memory) and inference time during the code orchestration process and report these metrics back to the frontend in the final result.

## 2. Proposed Solution
Implement a background `PerformanceTracker` utility that polls the NVIDIA Management Library (`pynvml`) for GPU statistics at regular intervals during the orchestration loop. Calculate averages for GPU utilization and memory usage, and measure the total elapsed time for all LLM generations.

## 3. Architecture & Components

### A. PerformanceTracker (`app/utils/performance.py`)
- **Responsibility:** Manage GPU polling and time tracking.
- **Mechanism:** 
    - Use `pynvml` (from `nvidia-ml-py`) to access the primary GPU (index 0).
    - Polling interval: 0.5 seconds (adjustable).
    - Collect utilization rates (%) and memory usage (%).
    - Calculate averages upon completion.
    - Measure total time from orchestration start to completion.

### B. Database Schema Update (`app/modules/context_manager.py`)
- **New Fields in `RefactorHistory`:**
    - `avg_gpu_utilization` (FloatField, nullable)
    - `avg_gpu_memory` (FloatField, nullable)
    - `inference_time` (FloatField, nullable)
- **Updated `complete_session`:** 
    - Accept performance metrics dictionary.
    - Update the new database fields.

### C. Connection Manager update (`app/modules/connection_manager.py`)
- **Updated `send_result`:**
    - Accept `performance_metrics` dict.
    - Include metrics in the WebSocket JSON message sent to the frontend.

### D. Orchestrator Integration (`app/modules/orchestrator.py`)
- **Workflow:**
    1. Initialize `PerformanceTracker` at the start of `execute_orchestration`.
    2. Start background tracking.
    3. Run the existing orchestration logic (Planning -> Refactoring -> Judging -> Validating).
    4. Stop tracking and capture metrics before sending final result.
    5. Pass metrics to `send_result`.

### E. API Schema Updates (`app/utils/schemas.py`)
- **Update `HistoryDetail`:**
    - Add the new performance fields to ensure the GET history endpoint returns them.

## 4. Error Handling
- **Missing GPU:** If `nvmlInit()` fails (no NVIDIA GPU), logging should catch the error and default metrics to 0 or null without crashing the orchestration.
- **Halted Orchestration:** If orchestration is halted, stop tracking immediately to release resources.

## 5. Success Criteria
- [ ] Final WebSocket `result` message contains `avg_gpu_utilization`, `avg_gpu_memory`, and `inference_time`.
- [ ] These three metrics are persisted in the `history.db` for each successful session.
- [ ] History detail endpoint (`/api/history/{id}`) includes the performance metrics.
