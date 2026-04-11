# Design Spec: Immediate Orchestration Halt (Backend)

**Status:** Draft
**Date:** 2026-04-11
**Topic:** Implementing a mechanism to immediately stop the orchestration process via a WebSocket signal.

## 1. Overview
Currently, the backend processes a `RefactorRequest` to completion without any way for the user to interrupt it. This spec introduces a `HaltRequest` sent via the existing WebSocket that triggers an immediate cancellation of the orchestration task.

## 2. Architecture & Data Flow

### 2.1 Message Protocol
The WebSocket protocol will be expanded to handle multiple message types from the client:

- **`RefactorRequest`**: Initiates the orchestration.
- **`HaltRequest`**: Cancels the currently active orchestration task for that connection.

```python
# app/utils/types.py additions
class HaltRequest(BaseModel):
    type: str = "halt"
```

### 2.2 Task-Based Cancellation (Approach 1)
In `app/main.py`, the orchestration call will be wrapped in an `asyncio.Task`.

1.  **Orchestration Task:** When a refactor request is validated, `orchestrator.execute_orchestration` is scheduled as a task: `current_task = asyncio.create_task(...)`.
2.  **Concurrency:** The WebSocket listener loop in `main.py` continues to listen for new messages while `current_task` is running.
3.  **Halt Handling:** If a message of type `"halt"` is received, the backend calls `current_task.cancel()`.

### 2.3 Sequence Diagram
[Visual Companion Diagram: http://localhost:53588/](http://localhost:53588/)

## 3. Component Details

### 3.1 `app/main.py` (Orchestration Management)
The `entrypoint` function will be refactored to:
- Maintain a reference to `current_task: Optional[asyncio.Task]`.
- Use a `while True` loop that `await websocket.receive_json()`.
- If type is `refactor`: Start the task.
- If type is `halt`: `current_task.cancel()`.

### 3.2 `app/modules/orchestrator.py` (Graceful Interruption)
The `execute_orchestration` method will be wrapped in a `try...except asyncio.CancelledError`:
- **Catching `CancelledError`**: 
    - Log a "Process Halted by User" status to the database.
    - Notify the frontend that the process has stopped.
- **`finally` block**: Ensure the `orchestration_lock` is released regardless of success, failure, or cancellation.

### 3.3 `app/modules/connection_manager.py`
Add a helper method `send_halt_notification()` to standardize the message format sent to the frontend when a halt occurs.

## 4. State & Database Integrity
- The database session for the refactoring will be marked as "Halted".
- Any partial code generated up to that point will remain in the logs for history, but the session status will be final.

## 5. Testing Strategy
- **Unit Test:** Mock the orchestrator and verify that sending a "halt" JSON payload triggers `task.cancel()`.
- **Integration Test:** Start a real orchestration (e.g., with a dummy model) and verify the `orchestration_lock` is released immediately after a "halt" command.
