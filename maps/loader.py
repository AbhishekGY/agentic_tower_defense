"""Map loader: builds GameMap from level definitions."""

from game.map_data import GameMap, Lane
from config import TILE_GROUND, TILE_PATH, TILE_BASE, TILE_SPAWN

G = TILE_GROUND
P = TILE_PATH
B = TILE_BASE
S = TILE_SPAWN

LEVELS = {
    "level1": {
        "width": 20,
        "height": 15,
        "grid": [
            [G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
            [S, P, P, P, P, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, P, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, P, P, P, P, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, P, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, P, P, P, P, P, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, G, G, G, G, P, G, G, G, G, G, G, G, G],
            [S, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, P, B, G],
            [G, G, G, G, G, G, G, G, G, G, G, P, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, P, P, P, P, P, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, P, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, P, P, P, P, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, P, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
            [S, P, P, P, P, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
            [G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G, G],
        ],
        "lanes": [
            {
                "name": "North",
                "spawn": (0, 1),
                "waypoints": [
                    (0, 1), (1, 1), (2, 1), (3, 1), (4, 1),
                    (4, 2), (4, 3), (5, 3), (6, 3), (7, 3),
                    (7, 4), (7, 5), (8, 5), (9, 5), (10, 5), (11, 5),
                    (11, 6), (11, 7), (12, 7), (13, 7), (14, 7),
                    (15, 7), (16, 7), (17, 7), (18, 7),
                ],
            },
            {
                "name": "Center",
                "spawn": (0, 7),
                "waypoints": [
                    (0, 7), (1, 7), (2, 7), (3, 7), (4, 7), (5, 7),
                    (6, 7), (7, 7), (8, 7), (9, 7), (10, 7), (11, 7),
                    (12, 7), (13, 7), (14, 7), (15, 7), (16, 7), (17, 7),
                    (18, 7),
                ],
            },
            {
                "name": "South",
                "spawn": (0, 13),
                "waypoints": [
                    (0, 13), (1, 13), (2, 13), (3, 13), (4, 13),
                    (4, 12), (4, 11), (5, 11), (6, 11), (7, 11),
                    (7, 10), (7, 9), (8, 9), (9, 9), (10, 9), (11, 9),
                    (11, 8), (11, 7), (12, 7), (13, 7), (14, 7),
                    (15, 7), (16, 7), (17, 7), (18, 7),
                ],
            },
        ],
    },
}


def load_map(name: str) -> GameMap:
    if name not in LEVELS:
        raise ValueError(f"Unknown map: {name}. Available: {list(LEVELS.keys())}")
    data = LEVELS[name]
    lanes = [
        Lane(
            name=l["name"],
            spawn=tuple(l["spawn"]),
            waypoints=[tuple(w) for w in l["waypoints"]],
        )
        for l in data["lanes"]
    ]
    return GameMap(
        width=data["width"],
        height=data["height"],
        grid=data["grid"],
        lanes=lanes,
        base_pos=(18, 7),
    )
