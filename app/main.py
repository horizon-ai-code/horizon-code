import json
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from app.modules.agent_service import AgentService
from app.modules.orchestrator import Orchestrator
from app.modules.validator import Validator
from app.modules.websocket_manager import WebSocketManager
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
websocket_manager: WebSocketManager = WebSocketManager()
orchestrator: Orchestrator = Orchestrator(
    agent_service=agent_service,
    validator=validator,
    websocket_manager=websocket_manager,
)


@app.websocket("/ws")
async def entrypoint(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            data: dict = await websocket.receive_json()
            validated: Optional[RefactorRequest] = await validate_request(
                websocket=websocket, data=data
            )

            if not validated:
                continue

            await orchestrator.execute_orchestration(
                websocket=websocket,
                user_code=validated.code,
                user_instruction=validated.user_instruction,
            )

    except WebSocketDisconnect as e:
        print(f"Connection disconnected: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await agent_service.unload()


async def validate_request(
    websocket: WebSocket, data: dict
) -> Optional[RefactorRequest]:
    try:
        return RefactorRequest(**data)
    except ValidationError as e:
        await websocket.send_json(
            {"type": "error", "message": "Invalid Data Format", "details": e.errors()}
        )
        return None
