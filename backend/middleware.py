from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Enforce a bounded body size even when clients omit Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int = 65_536) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                declared_length = int(raw_length)
            except ValueError:
                await self._send_error(send, 400, "Invalid Content-Length header.")
                return
            if declared_length < 0:
                await self._send_error(send, 400, "Invalid Content-Length header.")
                return
            if declared_length > self.max_bytes:
                await self._send_error(send, 413, "Request body exceeds 64 KiB.")
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._send_error(send, 413, "Request body exceeds 64 KiB.")
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _send_error(send: Send, status_code: int, detail: str) -> None:
        payload: dict[str, Any] = {"detail": detail}
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(encoded)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": encoded, "more_body": False})
