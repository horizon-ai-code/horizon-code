import asyncio
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.modules.agent_service import AgentService
from app.modules.connection_manager import ClientConnection, ConnectionManager
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.utils.types import RefactorRequest, Role

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


@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()

    client_conn: ClientConnection = connection.create_websocket_connection(
        websocket=websocket
    )

    try:
        while True:
            validated: Optional[RefactorRequest] = await get_validated_data(
                websocket=websocket
            )
            if not validated:
                continue

            if orchestration_lock.locked():
                await client_conn.send_status(
                    role=Role.System,
                    content="Server is currently busy with another request. Your request is in the queue and will start automatically when ready...",
                )

            # Ensure only one refactor request is processed at a time globally
            async with orchestration_lock:
                # Every new request in the same connection gets a unique ID
                client_conn.reset_id()
                await client_conn.send_connection_id()

                await orchestrator.execute_orchestration(
                    client=client_conn,
                    user_code=validated.code,
                    user_instruction=validated.user_instruction,
                )

    except WebSocketDisconnect as e:
        print(f"Connection disconnected: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Only unload if no one else is currently orchestrating
        if not orchestration_lock.locked():
            await agent_service.unload()


@app.get("/api/history")
async def get_history():
    return await connection.get_rest_history()


@app.get("/api/history/{history_id}")
async def get_history_detail(history_id: str):
    record = await connection.get_history_by_id(history_id)
    if not record:
        raise HTTPException(status_code=404, detail="Refactor history not found")
    return record


@app.delete("/api/history/{history_id}")
async def delete_history_detail(history_id: str):
    deleted = await connection.delete_history_by_id(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Refactor history not found")
    return {
        "status": "history_deleted",
        "message": f"Refactor history {history_id} deleted",
    }


async def get_validated_data(websocket: WebSocket) -> Optional[RefactorRequest]:
    """
    Handles raw reception, JSON decoding, and Pydantic validation.
    Returns None if any step fails, keeping the connection alive.
    """
    try:
        # Step 1: Try to receive and decode raw JSON
        # This prevents crashes from empty or malformed strings (Postman errors)
        data = await websocket.receive_json()

        # Step 2: Try to validate against the Pydantic model
        return RefactorRequest(**data)

    except WebSocketDisconnect:
        raise

    except ValidationError as e:
        await websocket.send_json(
            {"type": "error", "message": "Invalid data format", "details": e.errors()}
        )

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        await websocket.send_json(
            {"type": "error", "message": "Malformed JSON payload", "details": str(e)}
        )

    except Exception as e:
        # Catch-all for unexpected message issues
        print(f"Non-fatal message error: {e}")

    return None
