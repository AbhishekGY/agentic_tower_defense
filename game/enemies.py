"""Enemy entities that move along lane waypoints."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from config import ENEMY_TYPES


_next_id = 0


def _gen_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


@dataclass
class Enemy:
    id: int
    enemy_type: str
    lane_name: str
    waypoints: list[tuple[int, int]]
    hp: float = 0.0
    max_hp: float = 0.0
    speed: float = 0.0
    reward: int = 0
    x: float = 0.0
    y: float = 0.0
    waypoint_index: int = 0
    progress: float = 0.0  # 0-1 between current and next waypoint
    alive: bool = True
    reached_base: bool = False

    def __post_init__(self):
        stats = ENEMY_TYPES[self.enemy_type]
        if self.hp == 0:
            self.hp = stats["hp"]
        if self.max_hp == 0:
            self.max_hp = stats["hp"]
        if self.speed == 0:
            self.speed = stats["speed"]
        if self.reward == 0:
            self.reward = stats["reward"]
        if self.x == 0 and self.y == 0:
            self.x = float(self.waypoints[0][0])
            self.y = float(self.waypoints[0][1])

    @property
    def color(self) -> tuple[int, int, int]:
        return ENEMY_TYPES[self.enemy_type]["color"]

    def move(self):
        if not self.alive or self.reached_base:
            return

        remaining = self.speed * 0.5  # tiles to travel this tick

        while remaining > 0:
            if self.waypoint_index >= len(self.waypoints) - 1:
                self.reached_base = True
                return

            target = self.waypoints[self.waypoint_index + 1]
            dx = target[0] - self.x
            dy = target[1] - self.y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist <= remaining:
                # Reach this waypoint and spend leftover budget on the next one
                self.x = float(target[0])
                self.y = float(target[1])
                remaining -= dist
                self.waypoint_index += 1
            else:
                ratio = remaining / dist
                self.x += dx * ratio
                self.y += dy * ratio
                remaining = 0

    def take_damage(self, damage: float):
        self.hp -= damage
        if self.hp <= 0:
            self.hp = 0
            self.alive = False


def create_enemy(enemy_type: str, lane_name: str, waypoints: list[tuple[int, int]]) -> Enemy:
    return Enemy(
        id=_gen_id(),
        enemy_type=enemy_type,
        lane_name=lane_name,
        waypoints=waypoints,
    )
