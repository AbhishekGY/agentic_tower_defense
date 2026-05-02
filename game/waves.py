"""Wave definitions: progressively harder enemy waves."""

from dataclasses import dataclass


@dataclass
class WaveEntry:
    enemy_type: str
    count: int
    spawn_delay: int  # ticks between spawns
    lane_index: int


@dataclass
class Wave:
    number: int
    entries: list[WaveEntry]
    pause_after: int = 10  # ticks to pause before next wave


def get_waves() -> list[Wave]:
    return [
        # Wave 1: gentle intro — grunts on center lane
        Wave(1, [
            WaveEntry("grunt", 5, 3, 1),
        ]),
        # Wave 2: grunts on two lanes
        Wave(2, [
            WaveEntry("grunt", 4, 3, 0),
            WaveEntry("grunt", 4, 3, 2),
        ]),
        # Wave 3: first tank
        Wave(3, [
            WaveEntry("grunt", 6, 2, 1),
            WaveEntry("tank", 1, 6, 1),
        ]),
        # Wave 4: swarm rush
        Wave(4, [
            WaveEntry("swarm", 10, 1, 0),
            WaveEntry("swarm", 10, 1, 2),
        ]),
        # Wave 5: mixed multi-lane
        Wave(5, [
            WaveEntry("grunt", 5, 2, 0),
            WaveEntry("tank", 2, 5, 1),
            WaveEntry("grunt", 5, 2, 2),
        ]),
        # Wave 6: tank push
        Wave(6, [
            WaveEntry("tank", 3, 4, 0),
            WaveEntry("tank", 3, 4, 2),
        ]),
        # Wave 7: swarm + tanks
        Wave(7, [
            WaveEntry("swarm", 12, 1, 1),
            WaveEntry("tank", 2, 5, 0),
            WaveEntry("tank", 2, 5, 2),
        ]),
        # Wave 8: heavy all lanes
        Wave(8, [
            WaveEntry("grunt", 8, 2, 0),
            WaveEntry("grunt", 8, 2, 1),
            WaveEntry("grunt", 8, 2, 2),
            WaveEntry("tank", 2, 6, 1),
        ]),
        # Wave 9: swarm flood
        Wave(9, [
            WaveEntry("swarm", 15, 1, 0),
            WaveEntry("swarm", 15, 1, 1),
            WaveEntry("swarm", 15, 1, 2),
            WaveEntry("tank", 3, 4, 1),
        ]),
        # Wave 10: final wave — everything
        Wave(10, [
            WaveEntry("grunt", 10, 2, 0),
            WaveEntry("tank", 4, 3, 1),
            WaveEntry("swarm", 15, 1, 2),
            WaveEntry("tank", 3, 4, 0),
            WaveEntry("grunt", 10, 2, 2),
        ]),
    ]
