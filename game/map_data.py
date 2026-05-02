"""Map definition: grid, tile types, and lane waypoints."""

from dataclasses import dataclass
from config import TILE_GROUND, TILE_PATH, TILE_BASE, TILE_SPAWN


@dataclass
class Lane:
    name: str
    spawn: tuple[int, int]
    waypoints: list[tuple[int, int]]


@dataclass
class GameMap:
    width: int
    height: int
    grid: list[list[int]]
    lanes: list[Lane]
    base_pos: tuple[int, int]

    def tile_at(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return -1

    def is_buildable(self, x: int, y: int) -> bool:
        return self.tile_at(x, y) == TILE_GROUND

    def get_spawn_points(self) -> list[tuple[int, int]]:
        return [lane.spawn for lane in self.lanes]
