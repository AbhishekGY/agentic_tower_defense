"""Async Multi-Agent Tower Defense — Phase 1 Entry Point (Manual Play)"""

import argparse
import asyncio
import threading
import sys

import pygame

from game.state import GameState
from game.tick import game_tick_loop
from renderer.renderer import PygameRenderer
from maps.loader import load_map
from config import Config


def run_async_loop(game_state: GameState, config: Config):
    asyncio.run(game_tick_loop(game_state, config))


def main():
    parser = argparse.ArgumentParser(description="Async Multi-Agent Tower Defense")
    parser.add_argument("--map", default="level1", help="Map name to load")
    parser.add_argument("--speed", type=float, default=1.0, help="Game speed multiplier")
    args = parser.parse_args()

    config = Config(speed_multiplier=args.speed)
    game_map = load_map(args.map)
    game_state = GameState(game_map, config)

    async_thread = threading.Thread(
        target=run_async_loop,
        args=(game_state, config),
        daemon=True,
    )
    async_thread.start()

    renderer = PygameRenderer(game_state, message_bus=None, config=config)
    renderer.run()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
