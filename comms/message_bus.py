"""Async message bus for inter-agent communication."""
from __future__ import annotations
import asyncio
import threading
import time
from dataclasses import dataclass


@dataclass
class Message:
    sender: str
    content: str
    type: str       # "broadcast" | "direct" | "urgent"
    to: str | None  # recipient role (None for broadcast/urgent)
    tick: int
    timestamp: float


class MessageBus:
    ROLES = ["Scout", "Commander", "Builder"]

    def __init__(self, agent_roles: list[str] | None = None):
        self._roles = agent_roles or self.ROLES
        self._inboxes: dict[str, asyncio.Queue] = {}
        self._urgent_event: asyncio.Event | None = None
        self.history: dict[str, list[Message]] = {r: [] for r in self._roles}

        # Thread-safe display log — written by async thread, read by renderer (main thread)
        self._log_lock = threading.Lock()
        self._global_log: list[Message] = []

        # Agent status dict — written by agents, read by renderer
        self.agent_statuses: dict[str, dict] = {
            r: {"status": "Offline", "last_action": "-"}
            for r in self._roles
        }

    def initialize(self):
        """Create asyncio primitives — must be called from within the event loop."""
        self._inboxes = {r: asyncio.Queue() for r in self._roles}
        self._urgent_event = asyncio.Event()

    async def post(self, message: Message):
        with self._log_lock:
            self._global_log.append(message)
            if len(self._global_log) > 300:
                self._global_log = self._global_log[-300:]

        if message.type in ("broadcast", "urgent"):
            for role in self._roles:
                if role != message.sender:
                    await self._inboxes[role].put(message)
                    self.history[role].append(message)
            if message.type == "urgent":
                self._urgent_event.set()
        elif message.type == "direct" and message.to:
            await self._inboxes[message.to].put(message)
            self.history[message.to].append(message)

    async def read(self, agent_role: str) -> list[Message]:
        messages = []
        while not self._inboxes[agent_role].empty():
            messages.append(await self._inboxes[agent_role].get())
        return messages

    def get_display_log(self, last_n: int = 100) -> list[Message]:
        with self._log_lock:
            return list(self._global_log[-last_n:])

    @property
    def urgent_event(self) -> asyncio.Event:
        return self._urgent_event

    def clear_urgent(self):
        if self._urgent_event:
            self._urgent_event.clear()

    def update_status(self, role: str, status: str, last_action: str | None = None):
        self.agent_statuses[role]["status"] = status
        if last_action is not None:
            self.agent_statuses[role]["last_action"] = last_action
