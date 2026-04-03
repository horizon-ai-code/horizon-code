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

    async def send_status(self, role: Role, content: str) -> None:
        message: dict = {"type": "status", "role": role, "content": content}
        await self.websocket.send_json(message)

    async def send_result(
        self,
        final_code: str,
        insights: str,
        complexity: int,
        original_code: str,
        user_instruction: str,
    ):
        # 1. Save to the SQLite database using Peewee
        self.db.save_history(
            instruction=user_instruction,
            original=original_code,
            refactored=final_code,
            insights=insights,
            complexity=complexity,
        )

        # 2. Send the final result payload to the frontend
        message: dict = {
            "type": "result",
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

    async def get_rest_history(self) -> list[dict]:
        """
        Delegates the history fetching for the HTTP GET endpoint.
        """
        return self.db.get_history()

    def create_websocket_connection(self, websocket: WebSocket) -> ClientConnection:
        """
        Factory method: Builds the ClientConnection and safely injects
        the database manager into it.
        """
        return ClientConnection(websocket=websocket, db=self.db)
