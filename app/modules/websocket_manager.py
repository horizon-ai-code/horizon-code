from fastapi import WebSocket

from app.utils.types import Role


class ClientConnection:
    """
    Manages active WebSocket connections for real-time communication.
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def send_status(self, role: Role, content: str) -> None:

        message: dict = {"type": "status", "role": role, "content": content}

        await self.websocket.send_json(message)

    async def send_result(self, final_code: str, insights: str, complexity: int):
        message: dict = {
            "type": "result",
            "code": final_code,
            "complexity": complexity,
            "insights": insights,
        }

        await self.websocket.send_json(message)
