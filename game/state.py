"""Thread-safe game state with snapshot/apply pattern."""

from __future__ import annotations
import copy
import threading
from dataclasses import dataclass, field
from game.map_data import GameMap
from game.enemies import Enemy
from game.turrets import Turret
from config import TURRET_TYPES


@dataclass
class StateSnapshot:
    """Frozen read-only copy of game state."""
    tick: int
    enemies: list[Enemy]
    turrets: list[Turret]
    resources: int
    base_hp: int
    current_wave: int
    total_waves: int
    running: bool
    won: bool
    lost: bool
    game_map: GameMap
    recent_hits: list[tuple[tuple[float, float], tuple[float, float]]]


@dataclass
class Action:
    action_type: str  # "place_turret", "upgrade_turret", "sell_turret"
    turret_type: str | None = None
    x: int = 0
    y: int = 0


class GameState:
    def __init__(self, game_map: GameMap, config=None):
        from config import Config
        self.config = config or Config()
        self.game_map = game_map
        self._lock = threading.Lock()

        self.tick = 0
        self.enemies: list[Enemy] = []
        self.turrets: list[Turret] = []
        self.resources = self.config.starting_resources
        self.base_hp = self.config.base_hp
        self.current_wave = 0
        self.total_waves = self.config.total_waves
        self.running = True
        self.won = False
        self.lost = False
        self.recent_hits: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                tick=self.tick,
                enemies=copy.deepcopy(self.enemies),
                turrets=copy.deepcopy(self.turrets),
                resources=self.resources,
                base_hp=self.base_hp,
                current_wave=self.current_wave,
                total_waves=self.total_waves,
                running=self.running,
                won=self.won,
                lost=self.lost,
                game_map=self.game_map,
                recent_hits=list(self.recent_hits),
            )

    def apply(self, action: Action) -> tuple[bool, str]:
        with self._lock:
            return self._apply_locked(action)

    def _apply_locked(self, action: Action) -> tuple[bool, str]:
        if action.action_type == "place_turret":
            return self._place_turret(action)
        elif action.action_type == "upgrade_turret":
            return self._upgrade_turret(action)
        elif action.action_type == "sell_turret":
            return self._sell_turret(action)
        return False, f"Unknown action type: {action.action_type}"

    def _place_turret(self, action: Action) -> tuple[bool, str]:
        if action.turret_type not in TURRET_TYPES:
            return False, f"Unknown turret type: {action.turret_type}"
        cost = TURRET_TYPES[action.turret_type]["cost"]
        if self.resources < cost:
            return False, f"Not enough resources ({self.resources} < {cost})"
        if not self.game_map.is_buildable(action.x, action.y):
            return False, f"Tile ({action.x}, {action.y}) is not buildable"
        for t in self.turrets:
            if t.x == action.x and t.y == action.y:
                return False, f"Tile ({action.x}, {action.y}) already has a turret"
        self.resources -= cost
        self.turrets.append(Turret(x=action.x, y=action.y, turret_type=action.turret_type))
        return True, "OK"

    def _upgrade_turret(self, action: Action) -> tuple[bool, str]:
        for t in self.turrets:
            if t.x == action.x and t.y == action.y:
                if not t.can_upgrade():
                    return False, "Turret already at max level"
                cost = t.upgrade_cost()
                if self.resources < cost:
                    return False, f"Not enough resources ({self.resources} < {cost})"
                self.resources -= cost
                t.upgrade()
                return True, "OK"
        return False, f"No turret at ({action.x}, {action.y})"

    def _sell_turret(self, action: Action) -> tuple[bool, str]:
        for i, t in enumerate(self.turrets):
            if t.x == action.x and t.y == action.y:
                self.resources += t.sell_value
                self.turrets.pop(i)
                return True, "OK"
        return False, f"No turret at ({action.x}, {action.y})"

    def get_turret_at(self, x: int, y: int) -> Turret | None:
        with self._lock:
            for t in self.turrets:
                if t.x == x and t.y == y:
                    return t
            return None
