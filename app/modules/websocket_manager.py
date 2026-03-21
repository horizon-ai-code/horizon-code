from fastapi import WebSocket


class WebSocketManager:
    """
    Manages active WebSocket connections for real-time communication.
    """

    async def send_message(
        self,
        websocket: WebSocket,
        content: dict,
    ) -> None:
        """
        Sends a text message through an active WebSocket connection.

        Args:
            websocket: The WebSocket instance to send the message through.
            content: The dictionary content of the message.
        """

        await websocket.send_json(content)
