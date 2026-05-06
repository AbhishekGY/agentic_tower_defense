"""Base class for all agents (dummy and LLM-based)."""
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from game.state import GameState, Action, StateSnapshot
from comms.message_bus import MessageBus, Message

STALE_TICKS = 8  # messages older than this are annotated stale


class BaseAgent(ABC):
    role: str = ""
    think_interval: float = 4.0

    def format_messages(
        self,
        messages: list[Message],
        current_tick: int,
        message_bus: MessageBus | None = None,
    ) -> str:
        if not messages:
            return "  (no recent messages)"
        lines = []
        for msg in messages:
            age = current_tick - msg.tick
            is_stale = age > STALE_TICKS
            stale = " (stale)" if is_stale else ""
            if is_stale and message_bus is not None:
                message_bus.metrics.record_stale_read(self.role, age)
            if msg.type == "direct":
                lines.append(f"  [{age}t ago] {msg.sender}->you: \"{msg.content}\"{stale}")
            else:
                prefix = "URGENT" if msg.type == "urgent" else "broadcast"
                lines.append(f"  [{age}t ago] {msg.sender} ({prefix}): \"{msg.content}\"{stale}")
        return "\n".join(lines)

    def format_perception(self, snapshot: StateSnapshot, messages: list[Message]) -> str:
        """Build the text prompt for the LLM. Each subclass overrides this."""
        return self.format_messages(messages, snapshot.tick)

    @abstractmethod
    async def decide(
        self,
        snapshot: StateSnapshot,
        messages: list[Message],
    ) -> tuple[Action | None, Message | None]:
        """Return (action_to_apply, message_to_send). Either may be None."""
        raise NotImplementedError

    async def run(self, game_state: GameState, message_bus: MessageBus):
        self._message_bus = message_bus  # available to subclasses during decide()
        message_bus.update_status(self.role, "Starting")
        while game_state.running:
            message_bus.update_status(self.role, "Thinking...")
            snapshot = game_state.snapshot()
            messages = await message_bus.read(self.role)

            action, msg = await self.decide(snapshot, messages)

            if msg:
                await message_bus.post(msg)
                message_bus.update_status(self.role, "Messaging", msg.content[:50])

            if action:
                ok, reason = game_state.apply(action)
                if ok:
                    status = f"{action.action_type}@({action.x},{action.y})"
                else:
                    status = f"Failed: {reason[:35]}"
                message_bus.update_status(self.role, "Acting", status)
            elif not msg:
                message_bus.update_status(self.role, "Waiting")

            # Sleep until think_interval elapses, but wake early on urgent messages
            try:
                await asyncio.wait_for(
                    message_bus.urgent_event.wait(),
                    timeout=self.think_interval,
                )
                message_bus.clear_urgent()
            except asyncio.TimeoutError:
                pass

        message_bus.update_status(self.role, "Stopped")
