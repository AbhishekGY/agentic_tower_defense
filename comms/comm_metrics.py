"""Communication metrics tracker for Phase 4."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CommMetrics:
    # Messages sent per agent, by type
    sent: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            role: {"broadcast": 0, "direct": 0, "urgent": 0}
            for role in ("Scout", "Commander", "Builder")
        }
    )
    # Messages dropped by chaos config
    dropped: dict[str, int] = field(
        default_factory=lambda: {"Scout": 0, "Commander": 0, "Builder": 0}
    )
    # Urgent messages rate-limited (downgraded to broadcast)
    urgent_rate_limited: int = 0
    # Stale reads: (agent, tick_age) for each message read that was stale
    stale_reads: list[tuple[str, int]] = field(default_factory=list)
    # Protocol violations: (agent, description)
    protocol_violations: list[tuple[str, str]] = field(default_factory=list)
    # Urgent events fired
    urgent_events_fired: int = 0

    def record_sent(self, sender: str, msg_type: str):
        if sender in self.sent and msg_type in self.sent[sender]:
            self.sent[sender][msg_type] += 1

    def record_dropped(self, sender: str):
        if sender in self.dropped:
            self.dropped[sender] += 1

    def record_stale_read(self, reader: str, tick_age: int):
        self.stale_reads.append((reader, tick_age))

    def record_violation(self, agent: str, description: str):
        self.protocol_violations.append((agent, description))

    def summary(self) -> str:
        lines = ["=== Communication Metrics ==="]
        for role in ("Scout", "Commander", "Builder"):
            s = self.sent[role]
            d = self.dropped[role]
            total = sum(s.values())
            lines.append(
                f"  {role}: {total} sent "
                f"(bc={s['broadcast']}, dir={s['direct']}, urg={s['urgent']})"
                + (f" | {d} dropped" if d else "")
            )
        lines.append(f"  Stale reads: {len(self.stale_reads)}")
        lines.append(f"  Urgent rate-limited: {self.urgent_rate_limited}")
        if self.protocol_violations:
            lines.append(f"  Protocol violations: {len(self.protocol_violations)}")
            for agent, desc in self.protocol_violations[:5]:
                lines.append(f"    [{agent}] {desc}")
        return "\n".join(lines)
