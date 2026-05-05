"""Shared perception helpers — pure computation, no LLM or formatting."""
from __future__ import annotations
import math
from game.state import StateSnapshot


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def dist_to_base(enemy, game_map) -> float:
    bx, by = game_map.base_pos
    return dist(enemy.x, enemy.y, bx, by)


def enemies_per_lane(snapshot: StateSnapshot) -> dict[str, list]:
    result = {lane.name: [] for lane in snapshot.game_map.lanes}
    for e in snapshot.enemies:
        if e.alive and not e.reached_base and e.lane_name in result:
            result[e.lane_name].append(e)
    return result


def turrets_per_lane(snapshot: StateSnapshot) -> dict[str, list]:
    result = {lane.name: [] for lane in snapshot.game_map.lanes}
    covered: dict[str, set] = {lane.name: set() for lane in snapshot.game_map.lanes}
    for t in snapshot.turrets:
        tx, ty = t.x + 0.5, t.y + 0.5
        for lane in snapshot.game_map.lanes:
            if (t.x, t.y) in covered[lane.name]:
                continue
            for wx, wy in lane.waypoints:
                if dist(tx, ty, wx + 0.5, wy + 0.5) <= t.range:
                    result[lane.name].append(t)
                    covered[lane.name].add((t.x, t.y))
                    break
    return result


def buildable_near_lane(
    snapshot: StateSnapshot,
    lane_name: str,
    max_dist: float = 2.5,
) -> list[tuple[int, int]]:
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
                if dist(x + 0.5, y + 0.5, wx + 0.5, wy + 0.5) <= max_dist:
                    candidates.append((x, y))
                    break
    return candidates


def turret_lane_names(turret, snapshot: StateSnapshot) -> list[str]:
    """Return list of lane names that this turret covers."""
    tx, ty = turret.x + 0.5, turret.y + 0.5
    names = []
    for lane in snapshot.game_map.lanes:
        for wx, wy in lane.waypoints:
            if dist(tx, ty, wx + 0.5, wy + 0.5) <= turret.range:
                names.append(lane.name)
                break
    return names
