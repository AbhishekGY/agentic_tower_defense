"""Async message bus for inter-agent communication."""
from __future__ import annotations
import asyncio
import random
import threading
import time
from dataclasses import dataclass, field

from comms.comm_metrics import CommMetrics


@dataclass
class Message:
    sender: str
    content: str
    type: str       # "broadcast" | "direct" | "urgent"
    to: str | None  # recipient role (None for broadcast/urgent)
    tick: int
    timestamp: float


@dataclass
class BusConfig:
    """Toggleable communication chaos settings (Task 4.5)."""
    drop_rate: float = 0.0          # 0.0–1.0 fraction of non-urgent messages dropped
    delay_secs: float = 0.0         # seconds to delay delivery (simulates lag)
    silent_agents: set[str] = field(default_factory=set)  # outbound silenced
    urgent_cooldown_ticks: int = 5  # min ticks between urgent messages per sender


# Known protocol rules for violation detection
_PROTOCOL_RULES = {
    # Builder should not send urgent
    "Builder": {"forbidden_types": {"urgent"}},
    # Scout should not direct to Builder (chain of command)
    "Scout": {"forbidden_direct_targets": {"Builder"}},
}


class MessageBus:
    ROLES = ["Scout", "Commander", "Builder"]

    def __init__(self, agent_roles: list[str] | None = None, bus_config: BusConfig | None = None):
        self._roles = agent_roles or self.ROLES
        self._inboxes: dict[str, asyncio.Queue] = {}
        self._urgent_event: asyncio.Event | None = None
        self.history: dict[str, list[Message]] = {r: [] for r in self._roles}

        self.bus_config = bus_config or BusConfig()
        self.metrics = CommMetrics()

        # Urgent rate limiting: last tick an urgent was posted per sender
        self._last_urgent_tick: dict[str, int] = {}

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

    # ------------------------------------------------------------------
    # Protocol violation detection
    # ------------------------------------------------------------------

    def _check_violations(self, message: Message):
        rules = _PROTOCOL_RULES.get(message.sender, {})
        if message.type in rules.get("forbidden_types", set()):
            desc = f"sent forbidden type '{message.type}'"
            self.metrics.record_violation(message.sender, desc)
        if message.type == "direct" and message.to in rules.get("forbidden_direct_targets", set()):
            desc = f"sent direct to forbidden target '{message.to}'"
            self.metrics.record_violation(message.sender, desc)

    # ------------------------------------------------------------------
    # Delivery helpers
    # ------------------------------------------------------------------

    async def _deliver(self, role: str, message: Message):
        """Deliver a message to one inbox, applying delay and drop chaos."""
        cfg = self.bus_config

        # Drop non-urgent messages probabilistically
        if message.type != "urgent" and cfg.drop_rate > 0:
            if random.random() < cfg.drop_rate:
                self.metrics.record_dropped(message.sender)
                return

        if cfg.delay_secs > 0:
            await asyncio.sleep(cfg.delay_secs)

        await self._inboxes[role].put(message)
        self.history[role].append(message)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def post(self, message: Message):
        # Silence check
        if message.sender in self.bus_config.silent_agents:
            # Still log to display so renderer shows the silencing
            with self._log_lock:
                self._global_log.append(message)
                if len(self._global_log) > 300:
                    self._global_log = self._global_log[-300:]
            return

        # Check protocol violations
        self._check_violations(message)

        # Urgent rate limiting
        if message.type == "urgent":
            last = self._last_urgent_tick.get(message.sender, -999)
            cooldown = self.bus_config.urgent_cooldown_ticks
            if (message.tick - last) < cooldown:
                # Downgrade to broadcast
                message = Message(
                    sender=message.sender,
                    content=message.content,
                    type="broadcast",
                    to=None,
                    tick=message.tick,
                    timestamp=message.timestamp,
                )
                self.metrics.urgent_rate_limited += 1
            else:
                self._last_urgent_tick[message.sender] = message.tick
                self.metrics.urgent_events_fired += 1

        # Record in metrics
        self.metrics.record_sent(message.sender, message.type)

        # Append to display log
        with self._log_lock:
            self._global_log.append(message)
            if len(self._global_log) > 300:
                self._global_log = self._global_log[-300:]

        if message.type in ("broadcast", "urgent"):
            for role in self._roles:
                if role != message.sender:
                    await self._deliver(role, message)
            if message.type == "urgent":
                self._urgent_event.set()
        elif message.type == "direct" and message.to:
            await self._deliver(message.to, message)

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
