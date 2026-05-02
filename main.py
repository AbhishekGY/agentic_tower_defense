"""Async Multi-Agent Tower Defense — Entry Point"""

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


async def _run_with_agents(game_state: GameState, message_bus, config: Config):
    from agents.dummy_agents import ScoutDummy, CommanderDummy, BuilderDummy
    message_bus.initialize()
    await asyncio.gather(
        game_tick_loop(game_state, config),
        ScoutDummy().run(game_state, message_bus),
        CommanderDummy().run(game_state, message_bus),
        BuilderDummy().run(game_state, message_bus),
    )


def _run_async_loop(game_state: GameState, message_bus, config: Config):
    if config.mode == "dummy":
        asyncio.run(_run_with_agents(game_state, message_bus, config))
    else:
        asyncio.run(game_tick_loop(game_state, config))


def main():
    parser = argparse.ArgumentParser(description="Async Multi-Agent Tower Defense")
    parser.add_argument("--map", default="level1")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--mode", default="dummy", choices=["manual", "dummy"],
                        help="manual=click-to-place, dummy=AI agents (default)")
    args = parser.parse_args()

    config = Config(speed_multiplier=args.speed, mode=args.mode)
    game_map = load_map(args.map)
    game_state = GameState(game_map, config)

    message_bus = None
    if config.mode == "dummy":
        from comms.message_bus import MessageBus
        message_bus = MessageBus()

    async_thread = threading.Thread(
        target=_run_async_loop,
        args=(game_state, message_bus, config),
        daemon=True,
    )
    async_thread.start()

    renderer = PygameRenderer(game_state, message_bus=message_bus, config=config)
    renderer.run()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
