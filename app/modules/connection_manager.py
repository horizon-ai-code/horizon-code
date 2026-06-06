import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.modules.context_manager import DatabaseManager
from app.utils.types import Role


class ClientConnection:
    """
    Manages active WebSocket connections for real-time communication
    and handles history persistence.
    """

    def __init__(self, websocket: WebSocket, db: DatabaseManager):
        self.websocket = websocket
        self.db = db
        self.id = str(uuid.uuid4())

    async def _safe_send(self, message: dict) -> None:
        """Send JSON to frontend, silently handling disconnect."""
        try:
            await self.websocket.send_json(message)
        except WebSocketDisconnect:
            pass

    def reset_id(self) -> None:
        """Generates a new unique session ID for a new orchestration request."""
        self.id = str(uuid.uuid4())

    async def send_connection_id(self) -> None:
        """Sends the unique session ID to the frontend upon connection."""
        await self._safe_send({"type": "connection_id", "id": self.id})

    async def send_status(self, role: Role, content: str) -> None:
        await self._safe_send({"type": "status", "role": role, "content": content})

    async def send_halt_notification(self) -> None:
        await self._safe_send({
            "type": "status",
            "role": Role.System,
            "content": "Orchestration halted by user.",
        })

    async def send_result(
        self,
        final_code: str,
        original_complexity: int | None,
        refactored_complexity: int | None,
        performance_metrics: dict,
        exit_status: str = "SUCCESS",
        planner_model: str | None = None,
        generator_model: str | None = None,
        judge_model: str | None = None,
    ):
        """Sends the final result payload to the frontend."""
        await self._safe_send({
            "type": "result",
            "id": self.id,
            "code": final_code,
            "exit_status": exit_status,
            "original_complexity": original_complexity,
            "refactored_complexity": refactored_complexity,
            "performance": performance_metrics,
            "planner_model": planner_model,
            "generator_model": generator_model,
            "judge_model": judge_model,
        })

    async def send_insights(self, insights: Any):
        """Sends the structured insights follow-up message."""
        await self._safe_send({
            "type": "insights",
            "id": self.id,
            "insights": insights,
        })


class ConnectionManager:
    """
    The central gateway for all incoming API connections.
    Encapsulates database access so main.py remains clean.
    """

    def __init__(self):
        self.db = DatabaseManager()

    async def get_rest_history(self):
        return self.db.get_history()

    async def get_history_by_id(self, id: str) -> dict | None:
        return self.db.get_history_by_id(id)

    async def delete_history_by_id(self, id: str) -> bool:
        return self.db.delete_history_by_id(id)

    def create_websocket_connection(self, websocket: WebSocket) -> ClientConnection:
        return ClientConnection(websocket=websocket, db=self.db)
