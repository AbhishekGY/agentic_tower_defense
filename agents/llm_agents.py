"""LLM-driven agents using the Anthropic async SDK."""
from __future__ import annotations
import asyncio
import os
import time
import anthropic

from agents.base_agent import BaseAgent
from agents.perception import (
    dist_to_base,
    enemies_per_lane,
    turrets_per_lane,
    buildable_near_lane,
    turret_lane_names,
)
from agents.prompts import (
    SCOUT_SYSTEM_PROMPT, COMMANDER_SYSTEM_PROMPT, BUILDER_SYSTEM_PROMPT,
    SCOUT_TOOLS, COMMANDER_TOOLS, BUILDER_TOOLS,
)
from game.state import Action, StateSnapshot
from comms.message_bus import Message
from config import TURRET_TYPES


# Shared async client — safe to use across concurrent coroutines
_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            max_retries=2,  # SDK auto-retries 429 and 5xx
        )
    return _client


# ---------------------------------------------------------------------------
# LLM base
# ---------------------------------------------------------------------------

class LLMAgent(BaseAgent):
    model: str = "claude-haiku-4-5"
    max_tokens: int = 512
    _system_prompt: str = ""
    _tools: list = []

    async def _call_llm(self, user_content: str) -> anthropic.types.Message | None:
        try:
            response = await asyncio.wait_for(
                get_client().messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=[{
                        "type": "text",
                        "text": self._system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    tools=self._tools,
                    tool_choice={"type": "any"},
                    messages=[{"role": "user", "content": user_content}],
                ),
                timeout=15.0,
            )
            return response
        except asyncio.TimeoutError:
            return None
        except anthropic.RateLimitError:
            await asyncio.sleep(4.0)
            return None
        except anthropic.APIError:
            return None

    def _parse_response(
        self, response: anthropic.types.Message, snapshot: StateSnapshot
    ) -> tuple[Action | None, Message | None]:
        action: Action | None = None
        msg: Message | None = None

        for block in response.content:
            if block.type != "tool_use":
                continue
            inp = block.input

            if block.name == "send_message":
                msg = Message(
                    sender=self.role,
                    content=inp.get("content", ""),
                    type=inp.get("type", "broadcast"),
                    to=inp.get("to"),
                    tick=snapshot.tick,
                    timestamp=time.time(),
                )
            elif block.name == "place_turret":
                action = Action("place_turret", inp["type"], int(inp["x"]), int(inp["y"]))
            elif block.name == "upgrade_turret":
                action = Action("upgrade_turret", x=int(inp["x"]), y=int(inp["y"]))
            elif block.name == "sell_turret":
                action = Action("sell_turret", x=int(inp["x"]), y=int(inp["y"]))
            # "wait" → action stays None

        return action, msg

    async def decide(
        self, snapshot: StateSnapshot, messages: list[Message]
    ) -> tuple[Action | None, Message | None]:
        perception = self.format_perception(snapshot, messages)
        response = await self._call_llm(perception)
        if response is None:
            return None, None
        return self._parse_response(response, snapshot)


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

class ScoutLLM(LLMAgent):
    role = "Scout"
    think_interval = 2.0
    model = "claude-haiku-4-5"
    max_tokens = 256
    _system_prompt = SCOUT_SYSTEM_PROMPT
    _tools = SCOUT_TOOLS

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        epl = enemies_per_lane(snapshot)
        tpl = turrets_per_lane(snapshot)
        total = sum(len(v) for v in epl.values())

        lines = [
            f"BATTLEFIELD STATUS (tick={snapshot.tick}, wave={snapshot.current_wave}/{snapshot.total_waves})",
            "",
            f"ENEMIES ({total} alive):",
        ]
        if total == 0:
            lines.append("  (none on field)")
        else:
            for lane_name, enemies in epl.items():
                for e in enemies:
                    dtb = dist_to_base(e, snapshot.game_map)
                    lines.append(
                        f"  {e.enemy_type}_{e.id}: lane={lane_name} pos=({e.x:.1f},{e.y:.1f}) "
                        f"HP={e.hp:.0f}/{e.max_hp} speed={e.speed} dist_to_base={dtb:.1f}"
                    )

        lines += ["", "TURRET POSITIONS (locations only):"]
        if not snapshot.turrets:
            lines.append("  (none placed)")
        else:
            for t in snapshot.turrets:
                lane_names = turret_lane_names(t, snapshot)
                coverage = ", ".join(lane_names) if lane_names else "no lane"
                lines.append(f"  turret at ({t.x},{t.y}) — covers {coverage}")

        lines += ["", "COVERAGE GAPS:"]
        gaps = [l.name for l in snapshot.game_map.lanes if not tpl.get(l.name)]
        if gaps:
            for g in gaps:
                count = len(epl.get(g, []))
                lines.append(f"  {g} lane: NO COVERAGE" + (f" ({count} enemies incoming)" if count else ""))
        else:
            lines.append("  (all lanes have turret coverage)")

        lines += [
            "",
            f"BASE HP: {snapshot.base_hp}",
            "",
            "RECENT MESSAGES:",
            self.format_messages(messages[-5:], snapshot.tick, getattr(self, "_message_bus", None)),
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commander
# ---------------------------------------------------------------------------

class CommanderLLM(LLMAgent):
    role = "Commander"
    think_interval = 8.0
    model = "claude-sonnet-4-6"
    max_tokens = 512
    _system_prompt = COMMANDER_SYSTEM_PROMPT
    _tools = COMMANDER_TOOLS

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        epl = enemies_per_lane(snapshot)
        tpl = turrets_per_lane(snapshot)

        lines = [
            f"STRATEGIC OVERVIEW (tick={snapshot.tick}, wave={snapshot.current_wave}/{snapshot.total_waves})",
            "",
            "THREAT LEVELS BY LANE:",
        ]
        for lane in snapshot.game_map.lanes:
            enemies = epl.get(lane.name, [])
            count = len(enemies)
            defended = f"{len(tpl.get(lane.name, []))} turret(s)" if tpl.get(lane.name) else "UNDEFENDED ⚠"
            if count == 0:
                level = "LOW"
            elif count < 3:
                level = "MODERATE"
            else:
                level = "HIGH"
            types: dict[str, int] = {}
            for e in enemies:
                types[e.enemy_type] = types.get(e.enemy_type, 0) + 1
            type_str = ", ".join(f"{n} {t}" for t, n in types.items()) if types else "none"
            lines.append(f"  {lane.name:8}: {count} enemies ({type_str}) — {level} — {defended}")

        lines += ["", "DEFENSE STATUS:"]
        for lane in snapshot.game_map.lanes:
            turrets = tpl.get(lane.name, [])
            if turrets:
                t_desc = ", ".join(f"{t.turret_type}@({t.x},{t.y}) Lv{t.level}" for t in turrets)
                lines.append(f"  {lane.name}: {t_desc}")
            else:
                lines.append(f"  {lane.name}: NO COVERAGE")

        lines += [
            "",
            f"RESOURCES: {snapshot.resources} gold",
            f"BASE HP: {snapshot.base_hp}",
            f"WAVE: {snapshot.current_wave}/{snapshot.total_waves}",
            "",
            "RECENT MESSAGES (last 8):",
            self.format_messages(messages[-8:], snapshot.tick, getattr(self, "_message_bus", None)),
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class BuilderLLM(LLMAgent):
    role = "Builder"
    think_interval = 4.0
    model = "claude-haiku-4-5"
    max_tokens = 384
    _system_prompt = BUILDER_SYSTEM_PROMPT
    _tools = BUILDER_TOOLS

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        lines = [
            f"BUILD STATUS (tick={snapshot.tick}, wave={snapshot.current_wave}/{snapshot.total_waves})",
            "",
            f"RESOURCES: {snapshot.resources} gold",
            "",
            "BUILDABLE TILES (empty ground tiles, grouped by lane):",
        ]
        for lane in snapshot.game_map.lanes:
            tiles = buildable_near_lane(snapshot, lane.name)[:8]
            if tiles:
                tile_str = "  ".join(f"({x},{y})" for x, y in tiles)
                lines.append(f"  {lane.name} lane: {tile_str}")
            else:
                lines.append(f"  {lane.name} lane: (no free tiles nearby)")

        lines += ["", "TURRET COSTS:"]
        for ttype, stats in TURRET_TYPES.items():
            lines.append(
                f"  {ttype}: ${stats['cost']} "
                f"(dmg={stats['damage']}, range={stats['range']}, "
                f"splash={'yes' if stats['splash'] else 'no'})"
            )

        lines += ["", "EXISTING TURRETS:"]
        if snapshot.turrets:
            tpl = turrets_per_lane(snapshot)
            for t in snapshot.turrets:
                lane_names = [l for l, ts in tpl.items() if any(x.x == t.x and x.y == t.y for x in ts)]
                lane_str = lane_names[0] if lane_names else "unknown"
                upgrade_str = (
                    f" — upgrade: ${t.upgrade_cost()} (dmg {t.damage}→{t.damage + TURRET_TYPES[t.turret_type]['upgrade_damage']}, "
                    f"range {t.range}→{t.range + TURRET_TYPES[t.turret_type]['upgrade_range']})"
                    if t.can_upgrade() else " — MAX LEVEL"
                )
                lines.append(f"  {t.turret_type} at ({t.x},{t.y}) — {lane_str} lane — Lv{t.level}{upgrade_str}")
        else:
            lines.append("  (none placed yet)")

        lines += [
            "",
            f"BASE HP: {snapshot.base_hp}",
            "",
            "RECENT MESSAGES (last 5):",
            self.format_messages(messages[-5:], snapshot.tick, getattr(self, "_message_bus", None)),
        ]
        return "\n".join(lines)
