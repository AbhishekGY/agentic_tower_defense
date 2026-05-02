from dataclasses import dataclass, field


TILE_GROUND = 0
TILE_PATH = 1
TILE_BASE = 2
TILE_SPAWN = 3

ENEMY_TYPES = {
    "grunt": {
        "hp": 50,
        "speed": 1.5,
        "reward": 15,
        "color": (220, 50, 50),
    },
    "tank": {
        "hp": 200,
        "speed": 0.6,
        "reward": 40,
        "color": (50, 80, 220),
    },
    "swarm": {
        "hp": 25,
        "speed": 2.5,
        "reward": 8,
        "color": (50, 200, 80),
    },
}

TURRET_TYPES = {
    "basic": {
        "cost": 50,
        "damage": 20,
        "range": 3.0,
        "fire_rate": 1.0,  # shots per tick
        "splash": False,
        "color": (180, 180, 180),
        "upgrade_cost": 40,
        "upgrade_damage": 15,
        "upgrade_range": 0.5,
    },
    "splash": {
        "cost": 75,
        "damage": 12,
        "range": 2.5,
        "fire_rate": 0.8,
        "splash": True,
        "splash_radius": 1.5,
        "color": (220, 140, 40),
        "upgrade_cost": 60,
        "upgrade_damage": 8,
        "upgrade_range": 0.3,
    },
    "sniper": {
        "cost": 100,
        "damage": 60,
        "range": 5.0,
        "fire_rate": 0.4,
        "splash": False,
        "color": (140, 40, 220),
        "upgrade_cost": 80,
        "upgrade_damage": 30,
        "upgrade_range": 1.0,
    },
}


@dataclass
class Config:
    mode: str = "dummy"
    speed_multiplier: float = 1.0

    tick_interval_ms: int = 500

    grid_width: int = 20
    grid_height: int = 15
    tile_size: int = 40

    starting_resources: int = 200
    base_hp: int = 20
    total_waves: int = 10

    sell_refund_ratio: float = 0.5

    screen_width: int = 1400
    screen_height: int = 860

    @property
    def effective_tick_interval(self) -> float:
        return self.tick_interval_ms / 1000.0 / self.speed_multiplier
