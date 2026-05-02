"""Dummy agents for Phase 2 — rule-based, no LLM calls."""
from __future__ import annotations
import math
import re
import random
import time
from agents.base_agent import BaseAgent
from game.state import Action, StateSnapshot
from comms.message_bus import Message
from config import TURRET_TYPES


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _dist_to_base(enemy, game_map) -> float:
    bx, by = game_map.base_pos
    return _dist(enemy.x, enemy.y, bx, by)


def _enemies_per_lane(snapshot: StateSnapshot) -> dict[str, list]:
    result = {lane.name: [] for lane in snapshot.game_map.lanes}
    for e in snapshot.enemies:
        if e.alive and not e.reached_base and e.lane_name in result:
            result[e.lane_name].append(e)
    return result


def _turrets_per_lane(snapshot: StateSnapshot) -> dict[str, list]:
    """Map each lane name to the list of turrets that can reach any of its waypoints."""
    result = {lane.name: [] for lane in snapshot.game_map.lanes}
    covered: dict[str, set] = {lane.name: set() for lane in snapshot.game_map.lanes}

    for t in snapshot.turrets:
        tx, ty = t.x + 0.5, t.y + 0.5
        for lane in snapshot.game_map.lanes:
            if (t.x, t.y) in covered[lane.name]:
                continue
            for wx, wy in lane.waypoints:
                if _dist(tx, ty, wx + 0.5, wy + 0.5) <= t.range:
                    result[lane.name].append(t)
                    covered[lane.name].add((t.x, t.y))
                    break
    return result


def _buildable_near_lane(
    snapshot: StateSnapshot,
    lane_name: str,
    max_dist: float = 2.5,
) -> list[tuple[int, int]]:
    """Return unoccupied ground tiles within max_dist of any waypoint on the lane."""
    lane = next((l for l in snapshot.game_map.lanes if l.name == lane_name), None)
    if not lane:
        return []
    occupied = {(t.x, t.y) for t in snapshot.turrets}
    candidates = []
    for y in range(snapshot.game_map.height):
        for x in range(snapshot.game_map.width):
            if not snapshot.game_map.is_buildable(x, y):
                continue
            if (x, y) in occupied:
                continue
            for wx, wy in lane.waypoints:
                if _dist(x + 0.5, y + 0.5, wx + 0.5, wy + 0.5) <= max_dist:
                    candidates.append((x, y))
                    break
    return candidates


# ---------------------------------------------------------------------------
# Scout
# ---------------------------------------------------------------------------

class ScoutDummy(BaseAgent):
    role = "Scout"
    think_interval = 2.0

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        epl = _enemies_per_lane(snapshot)
        tpl = _turrets_per_lane(snapshot)
        lines = [
            f"BATTLEFIELD (tick={snapshot.tick}, wave={snapshot.current_wave}/{snapshot.total_waves})",
            "ENEMIES:",
        ]
        total = sum(len(v) for v in epl.values())
        if total == 0:
            lines.append("  (none alive)")
        else:
            for lane_name, enemies in epl.items():
                for e in enemies:
                    dtb = _dist_to_base(e, snapshot.game_map)
                    lines.append(
                        f"  {e.enemy_type}_{e.id}: lane={lane_name} "
                        f"pos=({e.x:.1f},{e.y:.1f}) HP={e.hp:.0f}/{e.max_hp} "
                        f"dist_to_base={dtb:.1f}"
                    )
        lines.append("COVERAGE GAPS:")
        gaps = [l.name for l in snapshot.game_map.lanes if not tpl.get(l.name)]
        if gaps:
            for g in gaps:
                lines.append(f"  {g} lane: NO COVERAGE")
        else:
            lines.append("  (all lanes covered)")
        lines.append(f"BASE HP: {snapshot.base_hp}")
        lines.append("MESSAGES:\n" + self.format_messages(messages, snapshot.tick))
        return "\n".join(lines)

    async def decide(self, snapshot: StateSnapshot, messages) -> tuple[Action | None, Message | None]:
        # Urgent: any enemy within 4 tiles of base
        near_base = [
            e for e in snapshot.enemies
            if e.alive and not e.reached_base and _dist_to_base(e, snapshot.game_map) < 4.0
        ]
        if near_base:
            closest = min(near_base, key=lambda e: _dist_to_base(e, snapshot.game_map))
            content = (
                f"ALERT: {closest.enemy_type} on {closest.lane_name} is "
                f"{_dist_to_base(closest, snapshot.game_map):.1f} tiles from base!"
            )
            return None, Message(
                sender="Scout", content=content, type="urgent",
                to=None, tick=snapshot.tick, timestamp=time.time(),
            )

        epl = _enemies_per_lane(snapshot)
        total = sum(len(v) for v in epl.values())
        if total == 0:
            return None, Message(
                sender="Scout", content="All clear — no enemies on field",
                type="broadcast", to=None,
                tick=snapshot.tick, timestamp=time.time(),
            )

        # Report highest-threat lane
        threat_lane = max(epl, key=lambda l: len(epl[l]))
        count = len(epl[threat_lane])
        types: dict[str, int] = {}
        for e in epl[threat_lane]:
            types[e.enemy_type] = types.get(e.enemy_type, 0) + 1
        type_str = ", ".join(f"{n} {t}" for t, n in types.items())
        content = f"{count} on {threat_lane} ({type_str})"
        return None, Message(
            sender="Scout", content=content, type="broadcast",
            to=None, tick=snapshot.tick, timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# Commander
# ---------------------------------------------------------------------------

class CommanderDummy(BaseAgent):
    role = "Commander"
    think_interval = 8.0

    def __init__(self):
        self._last_directive_tick: int = -999

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        epl = _enemies_per_lane(snapshot)
        tpl = _turrets_per_lane(snapshot)
        lines = [
            f"STRATEGIC OVERVIEW (tick={snapshot.tick}, wave={snapshot.current_wave}/{snapshot.total_waves})",
            "THREAT BY LANE:",
        ]
        for lane in snapshot.game_map.lanes:
            count = len(epl.get(lane.name, []))
            level = "HIGH" if count >= 3 else "MODERATE" if count >= 1 else "LOW"
            defended = "defended" if tpl.get(lane.name) else "UNDEFENDED"
            lines.append(f"  {lane.name}: {count} enemies — {level} — {defended}")
        lines.append(
            f"RESOURCES: {snapshot.resources} | BASE HP: {snapshot.base_hp} | "
            f"WAVE: {snapshot.current_wave}/{snapshot.total_waves}"
        )
        lines.append("MESSAGES:\n" + self.format_messages(messages, snapshot.tick))
        return "\n".join(lines)

    async def decide(self, snapshot: StateSnapshot, messages) -> tuple[Action | None, Message | None]:
        # Rate-limit directives to once per think_interval worth of ticks (~16 ticks at 0.5s)
        ticks_since_last = snapshot.tick - self._last_directive_tick
        if ticks_since_last < 14:
            return None, None

        epl = _enemies_per_lane(snapshot)
        tpl = _turrets_per_lane(snapshot)

        # Priority order: undefended + enemies > undefended > most enemies
        target_lane: str | None = None
        for lane in snapshot.game_map.lanes:
            if len(epl.get(lane.name, [])) > 0 and not tpl.get(lane.name):
                target_lane = lane.name
                break
        if not target_lane:
            for lane in snapshot.game_map.lanes:
                if not tpl.get(lane.name):
                    target_lane = lane.name
                    break
        if not target_lane:
            target_lane = max(epl, key=lambda l: len(epl[l]))

        tiles = _buildable_near_lane(snapshot, target_lane)
        if not tiles:
            return None, None

        # Pick from first 6 candidates
        tile = random.choice(tiles[:6])

        # Choose turret type by threat level
        enemy_count = len(epl.get(target_lane, []))
        if snapshot.resources >= TURRET_TYPES["splash"]["cost"] and enemy_count >= 3:
            turret_type = "splash"
        elif snapshot.resources >= TURRET_TYPES["sniper"]["cost"] and enemy_count == 0:
            turret_type = "sniper"
        else:
            turret_type = "basic"

        if snapshot.resources < TURRET_TYPES[turret_type]["cost"]:
            return None, None

        self._last_directive_tick = snapshot.tick
        content = f"Place {turret_type} at {tile[0]},{tile[1]} for {target_lane} lane"
        return None, Message(
            sender="Commander", content=content, type="direct",
            to="Builder", tick=snapshot.tick, timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class BuilderDummy(BaseAgent):
    role = "Builder"
    think_interval = 4.0

    def format_perception(self, snapshot: StateSnapshot, messages) -> str:
        occupied = {(t.x, t.y) for t in snapshot.turrets}
        lines = [f"BUILD STATUS (tick={snapshot.tick})"]
        lines.append(f"RESOURCES: {snapshot.resources}")
        lines.append("BUILDABLE TILES (sample):")
        count = 0
        for y in range(snapshot.game_map.height):
            for x in range(snapshot.game_map.width):
                if snapshot.game_map.is_buildable(x, y) and (x, y) not in occupied:
                    lines.append(f"  ({x},{y})")
                    count += 1
                    if count >= 8:
                        break
            if count >= 8:
                break
        lines.append(
            "COSTS: " + " | ".join(f"{t}=${v['cost']}" for t, v in TURRET_TYPES.items())
        )
        lines.append("EXISTING TURRETS:")
        if snapshot.turrets:
            for t in snapshot.turrets:
                lines.append(f"  {t.turret_type}@({t.x},{t.y}) Lv{t.level}")
        else:
            lines.append("  (none)")
        lines.append("MESSAGES:\n" + self.format_messages(messages, snapshot.tick))
        return "\n".join(lines)

    async def decide(self, snapshot: StateSnapshot, messages) -> tuple[Action | None, Message | None]:
        # Follow the most recent Commander direct directive
        directive = None
        for msg in reversed(messages):
            if msg.sender == "Commander" and msg.type == "direct":
                directive = msg.content
                break

        if directive:
            m = re.search(r"Place (\w+) at (\d+),(\d+)", directive)
            if m:
                turret_type = m.group(1)
                x, y = int(m.group(2)), int(m.group(3))
                if turret_type in TURRET_TYPES:
                    cost = TURRET_TYPES[turret_type]["cost"]
                    if snapshot.resources >= cost:
                        action = Action("place_turret", turret_type, x, y)
                        content = f"Placed {turret_type} at ({x},{y}) per Commander"
                        return action, Message(
                            sender="Builder", content=content, type="broadcast",
                            to=None, tick=snapshot.tick, timestamp=time.time(),
                        )

        # Self-directed: only spend if resources are comfortable
        min_reserve = TURRET_TYPES["basic"]["cost"] * 2
        if snapshot.resources < min_reserve:
            return None, None

        occupied = {(t.x, t.y) for t in snapshot.turrets}
        candidates = [
            (x, y)
            for y in range(snapshot.game_map.height)
            for x in range(snapshot.game_map.width)
            if snapshot.game_map.is_buildable(x, y) and (x, y) not in occupied
        ]
        if not candidates:
            return None, None

        tile = random.choice(candidates)
        turret_type = random.choice(["basic", "basic", "splash"])
        cost = TURRET_TYPES[turret_type]["cost"]
        if snapshot.resources >= cost:
            action = Action("place_turret", turret_type, tile[0], tile[1])
            content = f"Placed {turret_type} at {tile} (self-directed)"
            return action, Message(
                sender="Builder", content=content, type="broadcast",
                to=None, tick=snapshot.tick, timestamp=time.time(),
            )
        return None, None
