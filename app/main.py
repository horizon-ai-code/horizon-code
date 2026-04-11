import asyncio
import json
from typing import Optional, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError, UUID4

from app.modules.agent_service import AgentService
from app.modules.connection_manager import ClientConnection, ConnectionManager
from app.modules.context_manager import db
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.utils.types import RefactorRequest, Role
from app.utils.schemas import HistoryStub, HistoryDetail, DeleteResponse

app: FastAPI = FastAPI()

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

agent_service: AgentService = AgentService()
validator: Validator = Validator()
connection: ConnectionManager = ConnectionManager()
orchestrator: Orchestrator = Orchestrator(
    agent_service=agent_service, validator=validator, db=connection.db
)

# Global lock to serialize all orchestration (model & DB) operations
orchestration_lock = asyncio.Lock()


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


@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()

    client_conn: ClientConnection = connection.create_websocket_connection(
        websocket=websocket
    )
    current_task: Optional[asyncio.Task] = None

    async def run_orchestration(validated_data: RefactorRequest):
        try:
            # 1. New request cleanup
            client_conn.reset_id()
            await client_conn.send_connection_id()

            # 2. Sequential processing across ALL clients via global lock
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
            # Critical orchestration error
            print(f"Orchestration Task Failure (ID: {client_conn.id}): {e}")

    try:
        while True:
            # 1. Listen for raw messages
            try:
                data = await websocket.receive_json()
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                await websocket.send_json(
                    {"type": "error", "message": "Malformed JSON payload", "details": str(e)}
                )
                continue

            # 2. Handle 'halt' message
            if data.get("type") == "halt":
                if current_task and not current_task.done():
                    agent_service.stop()
                    print(f"Halt triggered for session {client_conn.id}")
                continue

            # 3. Handle RefactorRequest (backward compatibility: default type is refactor)
            try:
                validated = RefactorRequest(**data)
            except ValidationError as e:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid data format", "details": e.errors()}
                )
                continue

            # 4. Enforce one active orchestration per websocket connection
            if current_task and not current_task.done():
                await client_conn.send_status(
                    role=Role.System,
                    content="A refactor is already in progress. Please halt it first if you want to start a new one.",
                )
                continue

            # 5. Global lock status check (proactive notification)
            if orchestration_lock.locked():
                await client_conn.send_status(
                    role=Role.System,
                    content="Server is currently busy with another request. Your request is in the queue and will start automatically when ready...",
                )

            # 6. Offload orchestration to a background task
            current_task = asyncio.create_task(run_orchestration(validated))

    except WebSocketDisconnect as e:
        print(f"Connection disconnected: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if current_task and not current_task.done():
            agent_service.stop()

        # Only unload if no one else is currently orchestrating
        if not orchestration_lock.locked():
            await agent_service.unload()


@app.get("/api/history", response_model=List[HistoryStub], dependencies=[Depends(get_db)])
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
