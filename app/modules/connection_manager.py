import uuid
from typing import Optional

from fastapi import WebSocket

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

    def reset_id(self) -> None:
        """Generates a new unique session ID for a new orchestration request."""
        self.id = str(uuid.uuid4())

    async def send_connection_id(self) -> None:
        """Sends the unique session ID to the frontend upon connection."""
        message: dict = {"type": "connection_id", "id": self.id}
        await self.websocket.send_json(message)

    async def send_status(self, role: Role, content: str) -> None:
        message: dict = {"type": "status", "role": role, "content": content}
        await self.websocket.send_json(message)

    async def send_halt_notification(self) -> None:
        """Notifies the frontend that the orchestration has been halted."""
        message: dict = {"type": "status", "role": Role.System, "content": "Orchestration halted by user."}
        await self.websocket.send_json(message)

    async def send_result(
        self,
        final_code: str,
        insights: str,
        complexity: Optional[int],
    ):
        # 1. Update the existing session record with final results
        self.db.complete_session(
            id=self.id,
            refactored_code=final_code,
            insights=insights,
            complexity=complexity,
        )


        # 2. Send the final result payload to the frontend
        message: dict = {
            "type": "result",
            "id": self.id,
            "code": final_code,
            "complexity": complexity,
            "insights": insights,
        }
        await self.websocket.send_json(message)


class ConnectionManager:
    """
    The central gateway for all incoming API connections.
    Encapsulates database access so main.py remains clean.
    """

    def __init__(self):
        # The database is initialized here and hidden from the rest of the app
        self.db = DatabaseManager()

    async def get_rest_history(self):
        """
        Delegates the history fetching for the HTTP GET endpoint.
        """
        return self.db.get_history()

    async def get_history_by_id(self, id: str) -> Optional[dict]:
        """
        Delegates single history fetching.
        """
        return self.db.get_history_by_id(id)

    async def delete_history_by_id(self, id: str) -> bool:
        """
        Delegates single history deletion.
        """
        return self.db.delete_history_by_id(id)

    def create_websocket_connection(self, websocket: WebSocket) -> ClientConnection:
        """
        Factory method: Builds the ClientConnection and safely injects
        the database manager into it.
        """
        return ClientConnection(websocket=websocket, db=self.db)
