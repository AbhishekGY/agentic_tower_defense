"""Turret entities that target and damage enemies."""

from __future__ import annotations
import math
from dataclasses import dataclass
from config import TURRET_TYPES
from game.enemies import Enemy


@dataclass
class Turret:
    x: int
    y: int
    turret_type: str
    damage: float = 0.0
    range: float = 0.0
    fire_rate: float = 0.0
    splash: bool = False
    splash_radius: float = 0.0
    level: int = 1
    cooldown: float = 0.0  # ticks until next shot

    def __post_init__(self):
        stats = TURRET_TYPES[self.turret_type]
        if self.damage == 0:
            self.damage = stats["damage"]
        if self.range == 0:
            self.range = stats["range"]
        if self.fire_rate == 0:
            self.fire_rate = stats["fire_rate"]
        self.splash = stats.get("splash", False)
        self.splash_radius = stats.get("splash_radius", 0.0)

    @property
    def color(self) -> tuple[int, int, int]:
        return TURRET_TYPES[self.turret_type]["color"]

    @property
    def cost(self) -> int:
        return TURRET_TYPES[self.turret_type]["cost"]

    @property
    def sell_value(self) -> int:
        base = TURRET_TYPES[self.turret_type]["cost"]
        upgrade_cost = TURRET_TYPES[self.turret_type]["upgrade_cost"] * (self.level - 1)
        return int((base + upgrade_cost) * 0.5)

    def can_upgrade(self) -> bool:
        return self.level < 2

    def upgrade_cost(self) -> int:
        return TURRET_TYPES[self.turret_type]["upgrade_cost"]

    def upgrade(self):
        if not self.can_upgrade():
            return
        stats = TURRET_TYPES[self.turret_type]
        self.damage += stats["upgrade_damage"]
        self.range += stats["upgrade_range"]
        self.level += 1

    def distance_to(self, enemy: Enemy) -> float:
        dx = self.x + 0.5 - enemy.x
        dy = self.y + 0.5 - enemy.y
        return math.sqrt(dx * dx + dy * dy)

    def in_range(self, enemy: Enemy) -> bool:
        return self.distance_to(enemy) <= self.range

    def find_target(self, enemies: list[Enemy]) -> Enemy | None:
        best = None
        best_dist = float("inf")
        for e in enemies:
            if not e.alive:
                continue
            d = self.distance_to(e)
            if d <= self.range and d < best_dist:
                best = e
                best_dist = d
        return best

    def try_fire(self, enemies: list[Enemy]) -> list[tuple[Enemy, float]]:
        """Returns list of (enemy, damage_dealt) pairs. Empty if on cooldown or no target."""
        if self.cooldown > 0:
            self.cooldown -= 1
            return []

        target = self.find_target(enemies)
        if target is None:
            return []

        self.cooldown = max(0, (1.0 / self.fire_rate) - 1)
        hits = []

        if self.splash:
            for e in enemies:
                if not e.alive:
                    continue
                dx = target.x - e.x
                dy = target.y - e.y
                if math.sqrt(dx * dx + dy * dy) <= self.splash_radius:
                    e.take_damage(self.damage)
                    hits.append((e, self.damage))
        else:
            target.take_damage(self.damage)
            hits.append((target, self.damage))

        return hits
