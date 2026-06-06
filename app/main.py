import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import UUID4, ValidationError

from app.modules.agent_service import AgentService
from app.modules.connection_manager import ClientConnection, ConnectionManager
from app.modules.context_manager import db
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.utils.schemas import DeleteResponse, HistoryDetail, HistoryStub
from app.utils.types import RefactorRequest, Role

# Module-level singletons — initialized at import (lightweight, no model loaded).
# Override in tests by assigning to these variables directly.
agent_service: AgentService = AgentService()
validator: Validator = Validator()
connection: ConnectionManager = ConnectionManager()
orchestrator: Orchestrator = Orchestrator(
    agent_service=agent_service, validator=validator, db=connection.db
)

# Global lock to serialize all orchestration (model & DB) operations
orchestration_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: no-op (services init at module level).
    Shutdown: release loaded model VRAM.
    """
    yield
    await agent_service.unload()


app: FastAPI = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db():
    try:
        db.connect(reuse_if_open=True)
        yield
    finally:
        if not db.is_closed():
            db.close()


async def check_orchestration_lock():
    if orchestration_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System is currently busy with an active orchestration.",
        )


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = int((time.time() - start) * 1000)
    print(f"[{request.method}] {request.url.path} — {response.status_code} ({duration}ms)")
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()

    client_conn: ClientConnection = connection.create_websocket_connection(
        websocket=websocket
    )
    current_task: asyncio.Task | None = None

    async def run_orchestration(validated_data: RefactorRequest):
        try:
            client_conn.reset_id()
            await client_conn.send_connection_id()

            async with orchestration_lock:
                await orchestrator.execute_orchestration(
                    client=client_conn,
                    user_code=validated_data.code,
                    user_instruction=validated_data.user_instruction,
                )
        except asyncio.CancelledError:
            await client_conn.send_halt_notification()
            raise
        except Exception as e:
            print(f"Orchestration Task Failure (ID: {client_conn.id}): {e}")
            try:
                await client_conn.send_status(
                    Role.System,
                    f"Orchestration failed: {str(e)[:200]}",
                )
            except Exception:
                pass

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                await websocket.send_json(
                    {"type": "error", "message": "Malformed JSON payload", "details": str(e)}
                )
                continue

            if data.get("type") == "halt":
                if current_task and not current_task.done():
                    agent_service.stop()
                    current_task.cancel()
                    print(f"Halt triggered for session {client_conn.id}")
                await websocket.send_json({
                    "type": "halt_acknowledged",
                    "id": client_conn.id,
                })
                continue

            try:
                validated = RefactorRequest(**data)
            except ValidationError as e:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid data format", "details": e.errors()}
                )
                continue

            if current_task and not current_task.done():
                await client_conn.send_status(
                    role=Role.System,
                    content="A refactor is already in progress. Please halt it first if you want to start a new one.",
                )
                continue

            if orchestration_lock.locked():
                await client_conn.send_status(
                    role=Role.System,
                    content="Server is currently busy with another request. Your request is in the queue and will start automatically when ready...",
                )

            current_task = asyncio.create_task(run_orchestration(validated))

            # Notify frontend when the task actually starts processing
            async def notify_when_starting():
                while True:
                    if not orchestration_lock.locked():
                        await client_conn.send_status(
                            Role.System,
                            "Your request is now being processed...",
                        )
                        break
                    await asyncio.sleep(0.5)
            asyncio.create_task(notify_when_starting())

    except WebSocketDisconnect as e:
        print(f"Connection disconnected: {e}")
        if current_task and not current_task.done():
            agent_service.stop()
            current_task.cancel()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if current_task and not current_task.done():
            agent_service.stop()
            current_task.cancel()


@app.get("/api/history", response_model=list[HistoryStub], dependencies=[Depends(get_db)])
async def get_history():
    return await connection.get_rest_history()


@app.get(
    "/api/history/{history_id}",
    response_model=HistoryDetail,
    dependencies=[Depends(get_db)],
)
async def get_history_detail(
    history_id: UUID4, _=Depends(check_orchestration_lock)
):
    record = await connection.get_history_by_id(str(history_id))
    if not record:
        raise HTTPException(status_code=404, detail="Refactor history not found")
    return record


@app.delete(
    "/api/history/{history_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(get_db)],
)
async def delete_history_detail(
    history_id: UUID4, _=Depends(check_orchestration_lock)
):
    deleted = await connection.delete_history_by_id(str(history_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Refactor history not found")
    return {
        "status": "history_deleted",
        "message": f"Refactor history {history_id} deleted",
    }
