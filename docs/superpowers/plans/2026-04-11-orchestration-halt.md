# Orchestration Halt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement immediate halting of the orchestration process via a WebSocket "halt" signal.

**Architecture:** 
- Wrap `orchestrator.execute_orchestration` in an `asyncio.Task`.
- Use a `while True` loop in `app/main.py` to listen for both `RefactorRequest` and `HaltRequest`.
- Catch `asyncio.CancelledError` in `Orchestrator` to perform cleanup (DB log, lock release, frontend notification).

**Tech Stack:** FastAPI, asyncio, Peewee, llama-cpp-python.

---

### Task 1: Update Database Schema

**Files:**
- Modify: `app/modules/context_manager.py`

- [ ] **Step 1: Add `status` field to `RefactorHistory` model**

```python
class RefactorHistory(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    status = peewee.CharField(default="Processing") # Add this
    user_instruction = peewee.TextField()
    # ... rest ...
```

- [ ] **Step 2: Add `mark_as_halted` and `mark_as_failed` to `DatabaseManager`**

```python
    def mark_as_halted(self, id: str) -> None:
        """Updates session status to Halted."""
        with db.atomic():
            RefactorHistory.update(status="Halted").where(RefactorHistory.id == id).execute()

    def complete_session(self, id: str, ...) -> None:
        """Updates status to Completed and saves results."""
        with db.atomic():
            RefactorHistory.update(
                status="Completed",
                refactored_code=refactored_code,
                insights=insights,
                complexity=complexity,
            ).where(RefactorHistory.id == id).execute()
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/context_manager.py
git commit -m "feat(db): add status field and mark_as_halted method"
```

### Task 2: Update Types

**Files:**
- Modify: `app/utils/types.py`

- [ ] **Step 1: Add `HaltRequest` model**

```python
class HaltRequest(BaseModel):
    type: str
```

- [ ] **Step 2: Commit**

```bash
git add app/utils/types.py
git commit -m "feat(types): add HaltRequest model"
```

### Task 3: Update Connection Manager

**Files:**
- Modify: `app/modules/connection_manager.py`

- [ ] **Step 1: Add `send_halt_notification` method**

```python
    async def send_halt_notification(self) -> None:
        message: dict = {"type": "status", "role": Role.System, "content": "Orchestration halted by user."}
        await self.websocket.send_json(message)
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/connection_manager.py
git commit -m "feat(connection): add halt notification helper"
```

### Task 4: Update Orchestrator

**Files:**
- Modify: `app/modules/orchestrator.py`

- [ ] **Step 1: Handle `asyncio.CancelledError` in `execute_orchestration`**

```python
    async def execute_orchestration(self, client, user_code, user_instruction) -> None:
        try:
            # existing code...
        except asyncio.CancelledError:
            self.db.mark_as_halted(client.id)
            await self._notify(client, Role.System, "Process halted.")
            raise
        finally:
            await self.agent_service.unload()
```

- [ ] **Step 2: Commit**

```bash
git add app/modules/orchestrator.py
git commit -m "feat(orchestrator): handle task cancellation and mark DB as halted"
```

### Task 5: Refactor WebSocket Loop in `app/main.py`

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Implement concurrent listening for 'halt' messages**

```python
@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()
    client_conn = connection.create_websocket_connection(websocket)
    current_task = None

    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "halt":
                if current_task and not current_task.done():
                    current_task.cancel()
                continue

            # Process RefactorRequest
            validated = RefactorRequest(**data)
            
            # Use Task for orchestration to allow concurrent 'halt' checks
            async with orchestration_lock:
                client_conn.reset_id()
                await client_conn.send_connection_id()
                current_task = asyncio.create_task(orchestrator.execute_orchestration(client_conn, validated.code, validated.user_instruction))
                
                try:
                    await current_task
                except asyncio.CancelledError:
                    await client_conn.send_halt_notification()
    except Exception as e:
        print(f"WS Error: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add app/main.py
git commit -m "feat(main): support immediate halt via background tasks"
```

### Task 6: Verification

- [ ] **Step 1: Create a simulation script**
- [ ] **Step 2: Verify halt works and releases lock**
- [ ] **Step 3: Commit verification results**
