import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.modules.agent_service import AgentService
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.modules.websocket_manager import ClientConnection
from app.utils.types import RefactorRequest

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
orchestrator: Orchestrator = Orchestrator(
    agent_service=agent_service, validator=validator
)


@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()

    connection: ClientConnection = ClientConnection(websocket=websocket)

    try:
        while True:
            validated: Optional[RefactorRequest] = await get_validated_data(
                websocket=websocket
            )
            if not validated:
                continue

            await orchestrator.execute_orchestration(
                client=connection,
                user_code=validated.code,
                user_instruction=validated.user_instruction,
            )

    except WebSocketDisconnect as e:
        print(f"Connection disconnected: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await agent_service.unload()


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
