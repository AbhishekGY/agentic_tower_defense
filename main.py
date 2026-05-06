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
    # Phase 4: communication chaos flags
    parser.add_argument("--drop-rate", type=float, default=0.0, metavar="RATE",
                        help="Fraction of non-urgent messages to drop (0.0-1.0)")
    parser.add_argument("--delay", type=float, default=0.0, metavar="SECS",
                        help="Extra delivery delay in seconds for all messages")
    parser.add_argument("--silence", default="", metavar="AGENT",
                        help="Silence outbound messages from this agent (Scout/Commander/Builder)")
    args = parser.parse_args()

    config = Config(
        speed_multiplier=args.speed,
        mode=args.mode,
        comm_drop_rate=args.drop_rate,
        comm_delay_secs=args.delay,
        comm_silent_agent=args.silence,
    )
    game_map = load_map(args.map)
    game_state = GameState(game_map, config)

    message_bus = None
    if config.mode in ("dummy", "llm"):
        from comms.message_bus import MessageBus, BusConfig
        bus_config = BusConfig(
            drop_rate=config.comm_drop_rate,
            delay_secs=config.comm_delay_secs,
            silent_agents={config.comm_silent_agent} if config.comm_silent_agent else set(),
        )
        message_bus = MessageBus(bus_config=bus_config)

    async_thread = threading.Thread(
        target=_run_async_loop,
        args=(game_state, message_bus, config),
        daemon=True,
    )
    async_thread.start()

    renderer = PygameRenderer(game_state, message_bus=message_bus, config=config)
    renderer.run()

    # Print comm metrics summary after game ends
    if message_bus is not None:
        print("\n" + message_bus.metrics.summary())

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
