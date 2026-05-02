"""Game tick loop: moves enemies, fires turrets, spawns waves, checks win/lose."""

from __future__ import annotations
import asyncio
from game.state import GameState
from game.enemies import create_enemy
from game.waves import get_waves, Wave, WaveEntry
from config import Config


class WaveSpawner:
    def __init__(self, game_state: GameState):
        self.game_state = game_state
        self.waves = get_waves()
        self.current_wave_index = -1
        self.active_spawns: list[_SpawnTracker] = []
        self.pause_remaining = 0
        self.all_waves_launched = False

    def tick(self):
        if self.all_waves_launched and not self.active_spawns:
            return

        if self.pause_remaining > 0:
            self.pause_remaining -= 1
            return

        if not self.active_spawns and not self.all_waves_launched:
            self._start_next_wave()

        remaining = []
        for spawn in self.active_spawns:
            spawn.cooldown -= 1
            if spawn.cooldown <= 0 and spawn.remaining > 0:
                lane = self.game_state.game_map.lanes[spawn.entry.lane_index]
                enemy = create_enemy(
                    spawn.entry.enemy_type,
                    lane.name,
                    lane.waypoints,
                )
                self.game_state.enemies.append(enemy)
                spawn.remaining -= 1
                spawn.cooldown = spawn.entry.spawn_delay
            if spawn.remaining > 0:
                remaining.append(spawn)
        self.active_spawns = remaining

    def _start_next_wave(self):
        self.current_wave_index += 1
        if self.current_wave_index >= len(self.waves):
            self.all_waves_launched = True
            return

        wave = self.waves[self.current_wave_index]
        self.game_state.current_wave = wave.number
        self.active_spawns = [
            _SpawnTracker(entry=e, remaining=e.count, cooldown=0)
            for e in wave.entries
        ]
        if self.current_wave_index > 0:
            self.pause_remaining = self.waves[self.current_wave_index - 1].pause_after

    @property
    def all_enemies_done(self) -> bool:
        return (
            self.all_waves_launched
            and not self.active_spawns
            and all(not e.alive or e.reached_base for e in self.game_state.enemies)
        )


class _SpawnTracker:
    def __init__(self, entry: WaveEntry, remaining: int, cooldown: int):
        self.entry = entry
        self.remaining = remaining
        self.cooldown = cooldown


def process_tick(game_state: GameState, spawner: WaveSpawner):
    with game_state._lock:
        game_state.tick += 1
        game_state.recent_hits.clear()

        # 1. Spawn enemies
        spawner.tick()

        # 2. Move enemies
        for enemy in game_state.enemies:
            if enemy.alive and not enemy.reached_base:
                enemy.move()

        # 3. Fire turrets
        alive_enemies = [e for e in game_state.enemies if e.alive and not e.reached_base]
        for turret in game_state.turrets:
            hits = turret.try_fire(alive_enemies)
            for enemy, dmg in hits:
                game_state.recent_hits.append(
                    ((turret.x + 0.5, turret.y + 0.5), (enemy.x, enemy.y))
                )

        # 4. Remove dead enemies, award resources
        for enemy in game_state.enemies:
            if not enemy.alive and enemy.reward > 0:
                game_state.resources += enemy.reward
                enemy.reward = 0

        # 5. Check enemies reaching base
        for enemy in game_state.enemies:
            if enemy.reached_base and enemy.alive:
                game_state.base_hp -= 1
                enemy.alive = False

        # 6. Clean up dead/reached enemies periodically
        if game_state.tick % 10 == 0:
            game_state.enemies = [
                e for e in game_state.enemies
                if e.alive and not e.reached_base
            ]

        # 7. Check win/lose
        if game_state.base_hp <= 0:
            game_state.lost = True
            game_state.running = False

        if spawner.all_enemies_done and game_state.base_hp > 0:
            game_state.won = True
            game_state.running = False


async def game_tick_loop(game_state: GameState, config: Config):
    spawner = WaveSpawner(game_state)
    while game_state.running:
        process_tick(game_state, spawner)
        await asyncio.sleep(config.effective_tick_interval)
