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
    if config.mode == "llm":
        from agents.llm_agents import ScoutLLM, CommanderLLM, BuilderLLM
        scout, commander, builder = ScoutLLM(), CommanderLLM(), BuilderLLM()
    else:
        from agents.dummy_agents import ScoutDummy, CommanderDummy, BuilderDummy
        scout, commander, builder = ScoutDummy(), CommanderDummy(), BuilderDummy()

    message_bus.initialize()
    await asyncio.gather(
        game_tick_loop(game_state, config),
        scout.run(game_state, message_bus),
        commander.run(game_state, message_bus),
        builder.run(game_state, message_bus),
    )


def _run_async_loop(game_state: GameState, message_bus, config: Config):
    if config.mode in ("dummy", "llm"):
        asyncio.run(_run_with_agents(game_state, message_bus, config))
    else:
        asyncio.run(game_tick_loop(game_state, config))


def main():
    parser = argparse.ArgumentParser(description="Async Multi-Agent Tower Defense")
    parser.add_argument("--map", default="level1")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--mode", default="dummy", choices=["manual", "dummy", "llm"],
                        help="manual=click-to-place, dummy=rule-based agents, llm=LLM agents")
    args = parser.parse_args()

    config = Config(speed_multiplier=args.speed, mode=args.mode)
    game_map = load_map(args.map)
    game_state = GameState(game_map, config)

    message_bus = None
    if config.mode in ("dummy", "llm"):
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
