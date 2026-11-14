"""The one WebSocket at /ws: push the newest page state to every open page.

Bus threads call ClientHub.push() after any state change. Each page has a
one-slot queue, so a slow page skips stale states instead of building a backlog.
An open socket proves only that the page is connected to the dashboard.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

MIN_PUSH_INTERVAL_SECONDS = 0.1  # at most ten pushes a second per page


def _put_latest(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    """Replace whatever is waiting in a one-slot queue; stale state is useless."""
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(item)


class ClientHub:
    """Open pages and the event loop that serves them."""

    def __init__(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        """snapshot returns the current page state."""
        self._snapshot = snapshot
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def count(self) -> int:
        """Number of open pages."""
        return len(self._clients)

    def push(self) -> None:
        """Queue the new state for every open page; safe to call from any thread."""
        loop = self._loop
        if loop is None or not self._clients:
            return
        snapshot = self._snapshot()
        for queue in list(self._clients):
            with contextlib.suppress(RuntimeError):  # loop already closed at shutdown
                loop.call_soon_threadsafe(_put_latest, queue, snapshot)

    async def serve(self, websocket: WebSocket) -> None:
        """Send the state on connect and after every change until the page closes."""
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        self._clients.add(queue)
        receiver = asyncio.create_task(_wait_for_close(websocket))
        try:
            await websocket.send_json(self._snapshot())
            while not receiver.done():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    await websocket.send_json(getter.result())
                    await asyncio.sleep(MIN_PUSH_INTERVAL_SECONDS)
                else:
                    getter.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(queue)
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver


def build_realtime_router(hub: ClientHub) -> APIRouter:
    """Return the router holding /ws."""
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Stream page states to one page."""
        await hub.serve(websocket)

    return router


async def _wait_for_close(websocket: WebSocket) -> None:
    """Read and ignore anything the page sends; return when it disconnects."""
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()
