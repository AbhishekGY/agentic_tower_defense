# Async Multi-Agent Tower Defense

## Project Summary

A real-time tower defense game where 3 LLM agents (Scout, Commander, Builder) independently and asynchronously defend a base from waves of enemies. Each agent runs as a concurrent coroutine, makes decisions at its own pace, and communicates through a shared async message bus. No agent waits for another. Decisions are made on potentially stale information, forcing agents to reason under uncertainty.

**Core technical showcase:** True async multi-agent LLM orchestration with concurrent decision-making, shared state management, and unreliable-timing communication.

**Stack:** Python, Pygame, asyncio, Anthropic SDK (async), threading

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    asyncio Event Loop                         │
│                    (background thread)                        │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌────────────┐           │
│  │   Scout    │  │  Commander   │  │  Builder   │           │
│  │  Agent     │  │  Agent       │  │  Agent     │           │
│  │  Loop      │  │  Loop        │  │  Loop      │           │
│  │ (fast,~2s) │  │ (slow,~8s)   │  │ (med,~4s)  │           │
│  └─────┬──────┘  └──────┬───────┘  └─────┬──────┘           │
│        │                │                 │                   │
│        ▼                ▼                 ▼                   │
│  ┌─────────────────────────────────────────────────┐         │
│  │              Async Message Bus                   │         │
│  │  (asyncio.Queue per agent + broadcast channel)   │         │
│  └──────────────────────┬──────────────────────────┘         │
│                         │                                     │
│                         ▼                                     │
│  ┌─────────────────────────────────────────────────┐         │
│  │              Game State (shared)                  │         │
│  │  - Enemy positions & HP                          │         │
│  │  - Turret positions & stats                      │         │
│  │  - Resources                                     │         │
│  │  - Base HP                                       │         │
│  │  .snapshot() → frozen read-only copy              │         │
│  │  .apply(action) → validated mutation              │         │
│  └──────────────────────┬──────────────────────────┘         │
│                         │                                     │
│  ┌─────────────────────────────────────────────────┐         │
│  │              Game Tick Loop                       │         │
│  │  - Advances enemy movement                       │         │
│  │  - Fires turrets                                 │         │
│  │  - Spawns waves                                  │         │
│  │  - Checks win/lose                               │         │
│  │  Runs at fixed interval (~500ms per tick)         │         │
│  └─────────────────────────────────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                          │
                          │ state snapshots pushed via thread-safe queue
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                 Main Thread — Pygame                          │
│                                                              │
│  ┌─────────────────────────────────────────────────┐         │
│  │              Renderer                            │         │
│  │  - Map with paths and turret slots               │         │
│  │  - Enemy sprites moving along paths              │         │
│  │  - Turret sprites with fire animations           │         │
│  │  - Agent activity panel (who's thinking/acting)  │         │
│  │  - Message bus feed (scrolling chat sidebar)     │         │
│  │  - Resource counter, base HP, wave counter       │         │
│  └─────────────────────────────────────────────────┘         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Game Engine (No AI)

> Goal: A playable tower defense with manual turret placement and automated enemy waves.

### Task 1.1 — Map Definition
- Define a map as a 2D grid (e.g., 20x15)
- Tile types: path, ground (buildable), base, spawn point
- Enemy paths: predefined waypoint lists from spawn to base
- Support 2-3 lanes (paths) converging on the base
- Load maps from JSON/dict

### Task 1.2 — Enemy System
- Enemy class: position (float, for smooth movement along path), HP, speed, type, reward
- Enemy types:
  - `grunt` — low HP, fast, low reward
  - `tank` — high HP, slow, high reward
  - `swarm` — very low HP, very fast, spawns in groups
- Movement: enemies follow waypoints, interpolate between them each tick
- Death: enemy dies when HP ≤ 0, awards resources

### Task 1.3 — Turret System
- Turret class: position (grid cell), range, damage, fire rate, type
- Turret types:
  - `basic` — balanced range/damage, single target
  - `splash` — lower damage, hits area
  - `sniper` — high damage, long range, slow fire rate
- Targeting: each tick, turret picks nearest enemy in range, deals damage
- Placement: only on buildable tiles, costs resources

### Task 1.4 — Wave System
- Wave definition: list of (enemy_type, count, spawn_delay, lane)
- Waves get progressively harder (more enemies, tougher types, multi-lane)
- Brief pause between waves
- 8-10 waves total per game

### Task 1.5 — Game State Manager
- Central state object holding: enemies, turrets, resources, base HP, current wave, tick count
- `snapshot()` method: returns a deep-copied, read-only frozen state
- `apply(action)` method: validates and executes an action (place turret, upgrade turret, sell turret)
- Thread-safe: use `threading.Lock` around mutations

### Task 1.6 — Game Tick Loop
- Runs at fixed interval (e.g., 500ms per tick)
- Each tick:
  1. Move all enemies along their paths
  2. Fire all turrets at targets in range
  3. Remove dead enemies, award resources
  4. Check if any enemy reached the base → reduce base HP
  5. Check win (all waves cleared) / lose (base HP ≤ 0)
  6. Spawn next enemy in current wave if timer elapsed

### Task 1.7 — Pygame Renderer
- Render map grid with distinct colors per tile type
- Render enemies as colored circles moving smoothly along paths
- Render turrets as squares/icons on grid cells
- Render projectiles (optional, visual only)
- HUD: resources, base HP bar, wave number, tick count
- Manual mode: click to place turrets (for testing without AI)

---

## Phase 2: Async Infrastructure

> Goal: The concurrency layer that agents will run on. No LLM calls yet — test with dummy agents.

### Task 2.1 — Async Message Bus (Hybrid Protocol)

The message bus supports three message types: broadcast, direct, and urgent.

#### Message Types

| Type        | Routing                        | Use Case                                                    |
|-------------|--------------------------------|-------------------------------------------------------------|
| `broadcast` | Delivered to all agents        | Scout threat reports, Commander general strategy             |
| `direct`    | Delivered to one named agent   | Commander giving Builder a specific build order              |
| `urgent`    | Broadcast + interrupts sleeping agents | Scout warning that an enemy is about to reach the base |

#### Message Schema
```python
@dataclass
class Message:
    sender: str            # "Scout", "Commander", "Builder"
    content: str           # natural language message body
    type: str              # "broadcast", "direct", "urgent"
    to: str | None         # recipient role (None for broadcast/urgent)
    tick: int              # game tick when message was sent
    timestamp: float       # wall-clock time when message was sent
```

#### Bus Implementation
```python
class MessageBus:
    def __init__(self, agent_roles: list[str]):
        self.inboxes: dict[str, asyncio.Queue] = {
            role: asyncio.Queue() for role in agent_roles
        }
        self.urgent_event = asyncio.Event()
        self.history: dict[str, list[Message]] = {
            role: [] for role in agent_roles
        }

    async def post(self, message: Message):
        if message.type in ("broadcast", "urgent"):
            for role, inbox in self.inboxes.items():
                if role != message.sender:
                    await inbox.put(message)
                    self.history[role].append(message)
            if message.type == "urgent":
                self.urgent_event.set()
        elif message.type == "direct":
            await self.inboxes[message.to].put(message)
            self.history[message.to].append(message)

    async def read(self, agent_role: str) -> list[Message]:
        messages = []
        while not self.inboxes[agent_role].empty():
            messages.append(await self.inboxes[agent_role].get())
        return messages

    async def get_history(self, agent_role: str, last_n: int = 10) -> list[Message]:
        return self.history[agent_role][-last_n:]

    def clear_urgent(self):
        self.urgent_event.clear()
```

#### Key Design Decisions
- **Per-agent inbox**: each agent has its own `asyncio.Queue`. Agents only see messages routed to them — no global log access
- **Private history**: `self.history[role]` stores only messages that agent actually received. When building an agent's LLM prompt, pull from its history only — this maintains information asymmetry
- **Urgent interrupt**: `urgent_event` is an `asyncio.Event`. Sleeping agents `await asyncio.wait` on both their sleep timer and the urgent event — whichever fires first wakes them
- **Message expiry**: messages older than N ticks are pruned from history on read to prevent unbounded growth
- **No global visibility**: there is no method to read all messages across all agents. This is intentional — no agent should have full communication awareness

#### Agent Sleep with Urgent Interrupt
```python
async def run(self, game_state, message_bus):
    while game.running:
        snapshot = game_state.snapshot()
        messages = await message_bus.read(self.role)
        prompt = self.observe(snapshot, messages)
        action = await self.decide(prompt)
        success = await self.act(action, game_state)
        
        # Sleep, but wake early on urgent messages
        try:
            await asyncio.wait_for(
                message_bus.urgent_event.wait(),
                timeout=self.think_interval
            )
            message_bus.clear_urgent()
        except asyncio.TimeoutError:
            pass  # normal wake — think interval elapsed
```

#### LLM Output Format for Messaging
Each agent's LLM response includes an optional message alongside its action:
```json
{
  "action": { ... },
  "message": {
    "type": "direct",
    "to": "Builder",
    "content": "Place splash turret at (5,3) to cover north lane convergence point"
  }
}
```
Or broadcast:
```json
{
  "action": { ... },
  "message": {
    "type": "broadcast",
    "content": "Wave 4 incoming: 3 tanks on north lane, 5 grunts on south"
  }
}
```
Or no message (agent acts silently):
```json
{
  "action": { ... },
  "message": null
}
```

### Task 2.2 — Agent Base Class
```python
class BaseAgent:
    role: str
    think_interval: float  # seconds between decisions

    async def observe(self, state_snapshot, messages) -> str  # build prompt
    async def decide(self, prompt) -> Action                  # call LLM
    async def act(self, action, game_state) -> bool           # apply action
    async def run(self, game_state, message_bus):             # main loop
        while game.running:
            snapshot = game_state.snapshot()
            messages = await message_bus.read(self.role)
            prompt = self.observe(snapshot, messages)
            action = await self.decide(prompt)
            success = await self.act(action, game_state)
            await message_bus.post(self.role, str(action))
            await asyncio.sleep(self.think_interval)
```

### Task 2.3 — Dummy Agents for Testing
- ScoutDummy: reads state, posts "enemies detected at lane X" every 2 seconds
- CommanderDummy: reads messages, posts "focus lane X" every 8 seconds
- BuilderDummy: reads messages, places a random valid turret every 4 seconds
- Purpose: validate the async loop, message bus, and state management without LLM cost

### Task 2.4 — Main Loop Integration
```python
async def async_main(game_state, message_bus):
    await asyncio.gather(
        scout.run(game_state, message_bus),
        commander.run(game_state, message_bus),
        builder.run(game_state, message_bus),
        game_tick_loop(game_state),
    )

def main():
    # Pygame on main thread
    # asyncio on background thread
    game_state = GameState(load_map("level1"))
    message_bus = MessageBus()
    
    async_thread = threading.Thread(
        target=lambda: asyncio.run(async_main(game_state, message_bus))
    )
    async_thread.start()
    
    pygame_loop(game_state, message_bus)  # blocks on main thread
```

### Task 2.5 — State Snapshot Thread Safety
- `game_state.snapshot()` acquires a lock, deep copies, releases
- `game_state.apply(action)` acquires a lock, validates, mutates, releases
- Snapshots are frozen — agents can hold references without worrying about mutation
- Test: run 3 dummy agents + game loop concurrently for 100 ticks, assert no crashes or data corruption

### Task 2.6 — Perception Layer (Agent–Environment Interface)

This is how agents "see" and "act." There is no sensor simulation — agents receive formatted text derived from the game state snapshot, filtered by role. Each agent subclass implements `format_perception()` which takes the same raw snapshot and produces a different text view.

#### Architecture

```python
class BaseAgent:
    def format_perception(self, snapshot: GameStateSnapshot, messages: list[Message]) -> str:
        """Each subclass overrides this to show only role-appropriate info."""
        raise NotImplementedError

    def format_messages(self, messages: list[Message], current_tick: int) -> str:
        """Format inbox messages with staleness annotations."""
        lines = []
        for msg in messages:
            age = current_tick - msg.tick
            stale = " (⚠ stale)" if age > 8 else ""
            if msg.type == "direct":
                lines.append(f"[{age} ticks ago] {msg.sender} → you: \"{msg.content}\"{stale}")
            else:
                prefix = "🚨 URGENT" if msg.type == "urgent" else "broadcast"
                lines.append(f"[{age} ticks ago] {msg.sender} ({prefix}): \"{msg.content}\"{stale}")
        return "\n".join(lines) if lines else "(no recent messages)"
```

#### Scout Perception — Full Enemy Detail, No Build Info

The Scout sees everything about enemies but nothing about resources or buildable tiles.

```python
class ScoutAgent(BaseAgent):
    def format_perception(self, snapshot, messages):
        return f"""
BATTLEFIELD STATUS (tick {snapshot.tick}, wave {snapshot.wave}/{snapshot.total_waves}):

ENEMIES:
{self._format_enemies(snapshot.enemies)}

TURRET POSITIONS (you can see locations, not stats):
{self._format_turret_positions(snapshot.turrets)}

COVERAGE GAPS:
{self._identify_gaps(snapshot.turrets, snapshot.lanes)}

BASE HP: {snapshot.base_hp}/{snapshot.base_max_hp}

RECENT MESSAGES:
{self.format_messages(messages, snapshot.tick)}
"""

    def _format_enemies(self, enemies):
        # "grunt_12: lane=north, position=(8,3), HP=30/50, speed=1.5, distance_to_base=7 tiles"
        ...

    def _identify_gaps(self, turrets, lanes):
        # "Center lane: NO turret coverage"
        ...
```

Example Scout perception:
```
BATTLEFIELD STATUS (tick 47, wave 3/10):

ENEMIES:
  - grunt_12: lane=north, position=(8,3), HP=30/50, speed=1.5, distance_to_base=7 tiles
  - tank_04: lane=south, position=(4,7), HP=200/200, speed=0.5, distance_to_base=11 tiles
  - grunt_13: lane=north, position=(6,3), HP=50/50, speed=1.5, distance_to_base=9 tiles
  - grunt_14: lane=center, position=(9,5), HP=50/50, speed=1.5, distance_to_base=6 tiles

TURRET POSITIONS (you can see locations, not stats):
  - turret at (5,2): covering north lane
  - turret at (7,6): covering south lane

COVERAGE GAPS:
  - Center lane: NO turret coverage

BASE HP: 85/100

RECENT MESSAGES:
  [4 ticks ago] Commander (broadcast): "Prioritize north lane defense"
```

#### Commander Perception — Summaries, No Raw Data

The Commander does NOT see individual enemy positions or buildable tiles. It sees aggregated threat levels and resource status. It relies on Scout reports for battlefield details.

```python
class CommanderAgent(BaseAgent):
    def format_perception(self, snapshot, messages):
        return f"""
STRATEGIC OVERVIEW (tick {snapshot.tick}, wave {snapshot.wave}/{snapshot.total_waves}):

THREAT LEVELS BY LANE:
{self._format_threat_summary(snapshot.enemies, snapshot.lanes)}

DEFENSE STATUS:
{self._format_defense_summary(snapshot.turrets)}

RESOURCES: {snapshot.resources} gold (estimated income: ~{snapshot.income_rate} gold/wave)
BASE HP: {snapshot.base_hp}/{snapshot.base_max_hp}

WAVE SCHEDULE:
  Current: {snapshot.wave_description}
  Next: {snapshot.next_wave_preview}

RECENT MESSAGES:
{self.format_messages(messages, snapshot.tick)}
"""

    def _format_threat_summary(self, enemies, lanes):
        # "North: 2 enemies (1 damaged), MODERATE threat"
        # "South: 1 tank, HIGH threat"
        # "Center: 2 enemies, MODERATE threat, ⚠ UNDEFENDED"
        ...
```

Example Commander perception:
```
STRATEGIC OVERVIEW (tick 47, wave 3/10):

THREAT LEVELS BY LANE:
  North: 2 enemies (1 damaged), MODERATE threat — 1 turret covering
  South: 1 tank, HIGH threat — 1 turret covering
  Center: 2 enemies, MODERATE threat — ⚠ UNDEFENDED

DEFENSE STATUS:
  North lane: 1 turret (basic)
  South lane: 1 turret (sniper)
  Center lane: NO COVERAGE

RESOURCES: 350 gold (estimated income: ~50 gold/wave)
BASE HP: 85/100

WAVE SCHEDULE:
  Current: wave 3 — mixed grunts and tanks, multi-lane
  Next: wave 4 — heavy tank wave (north + south)

RECENT MESSAGES:
  [3 ticks ago] Scout (broadcast): "Center lane undefended, 2 grunts incoming, 6 tiles from base"
  [1 tick ago] Builder (broadcast): "350 gold available, awaiting orders"
```

#### Builder Perception — Build Options, No Enemy Detail

The Builder sees resources, buildable tiles, turret costs, and existing turrets with upgrade options. It does NOT see individual enemies — it relies on Scout and Commander messages for threat info.

```python
class BuilderAgent(BaseAgent):
    def format_perception(self, snapshot, messages):
        return f"""
BUILD STATUS (tick {snapshot.tick}, wave {snapshot.wave}/{snapshot.total_waves}):

RESOURCES: {snapshot.resources} gold

BUILDABLE TILES:
{self._format_buildable(snapshot.buildable_tiles, snapshot.lanes)}

TURRET COSTS:
  basic:  100 gold (dmg=10, range=3, single target)
  splash: 150 gold (dmg=5,  range=2, area damage)
  sniper: 200 gold (dmg=25, range=5, slow fire rate)

EXISTING TURRETS:
{self._format_existing_turrets(snapshot.turrets)}

BASE HP: {snapshot.base_hp}/{snapshot.base_max_hp}

RECENT MESSAGES:
{self.format_messages(messages, snapshot.tick)}
"""

    def _format_buildable(self, tiles, lanes):
        # "(3,2) — covers north lane"
        # "(6,4) — covers center lane"
        ...

    def _format_existing_turrets(self, turrets):
        # "basic at (5,2) — north lane — can upgrade for 75 gold (dmg 10→18, range 3→4)"
        ...
```

Example Builder perception:
```
BUILD STATUS (tick 47, wave 3/10):

RESOURCES: 350 gold

BUILDABLE TILES:
  (3,2) — covers north lane
  (3,4) — covers north lane
  (5,5) — covers center lane
  (6,4) — covers center lane
  (8,6) — covers south lane
  (10,3) — covers center + south lane overlap

TURRET COSTS:
  basic:  100 gold (dmg=10, range=3, single target)
  splash: 150 gold (dmg=5,  range=2, area damage)
  sniper: 200 gold (dmg=25, range=5, slow fire rate)

EXISTING TURRETS:
  basic at (5,2) — north lane — can upgrade for 75 gold (dmg 10→18, range 3→4)
  sniper at (7,6) — south lane — can upgrade for 150 gold (dmg 25→40, range 5→6)

BASE HP: 85/100

RECENT MESSAGES:
  [2 ticks ago] Commander → you: "Place splash at (6,4) to cover center lane"
  [5 ticks ago] Scout (broadcast): "Center lane undefended, 2 grunts incoming"
```

#### Why This Design Matters

- **Information asymmetry is enforced at the perception layer, not by trusting the LLM.** Even if an agent's system prompt says "you can't see enemies," the data simply isn't in its prompt. It can't hallucinate what it was never given.
- **The same snapshot feeds all agents.** `game_state.snapshot()` is called once per agent cycle. Each `format_perception()` filters it differently. No separate sensor systems needed.
- **Message context is the bridge.** The Commander can't see enemies directly, but it reads Scout messages that describe them. If the Scout is slow or down, the Commander operates blind. This is where async timing creates real consequences.
- **Perception formatting is tunable.** Want to make the game harder? Reduce Scout's perception radius. Want to test communication dependency? Strip turret info from the Commander's view entirely. These are just string formatting changes, not architectural ones.

---

## Phase 3: LLM Agent Integration

> Goal: Replace dummy agents with real LLM-driven agents.

### Task 3.1 — Prompt Design: Scout Agent
System prompt:
- You are a Scout. Your job is to observe the battlefield and report threats.
- You see the current enemy positions, types, HP, and which lanes they're on.
- You communicate findings to Commander and Builder via short messages.
- You do NOT place turrets or make strategic decisions.
- Be concise. Max 80 tokens per message.

Per-turn context:
- Current tick and wave number
- All enemy positions, types, HP, speeds
- Current turret positions and their coverage gaps
- Recent messages from other agents (last 5)

Output format:
- A message to broadcast (threat assessment, warnings)

### Task 3.2 — Prompt Design: Commander Agent
System prompt:
- You are the Commander. You set strategy and priorities.
- You read Scout reports and decide which lanes/threats to prioritize.
- You tell the Builder where to place turrets and what type.
- You do NOT directly place turrets or observe enemies — you rely on Scout reports.
- Your information may be stale. Acknowledge uncertainty.

Per-turn context:
- Current resources, base HP, wave number
- Current turret layout
- Recent messages from Scout and Builder (last 5-8)
- Summary of what happened since your last decision

Output format:
- A strategic directive broadcast ("prioritize north lane with splash turrets, save resources for wave 6")

### Task 3.3 — Prompt Design: Builder Agent
System prompt:
- You are the Builder. You place and upgrade turrets.
- You read Commander directives and act on them.
- If no directive is available or the situation is urgent, use your own judgment.
- You know the current resources and valid build locations.
- You must balance spending now vs. saving for later waves.

Per-turn context:
- Current resources
- Valid build locations (empty buildable tiles)
- Existing turrets and their stats
- Recent messages from Scout and Commander (last 5)
- Commander's latest directive

Output format:
- An action: `place_turret(type, position)` or `upgrade_turret(position)` or `sell_turret(position)` or `wait`

### Task 3.4 — Async LLM Calls
- Use Anthropic async SDK: `await client.messages.create(...)`
- Each agent uses tool-use format with both action tools and messaging tools:

**All agents share these messaging tools:**
```
send_message(type: "broadcast"|"direct"|"urgent", to: str|null, content: str)
```
- `to` is required when type is "direct", ignored otherwise
- `content` is capped at 100 tokens to force concise communication
- Agent can call `send_message` alongside an action tool in the same turn, or call it alone

**Scout tools:**
- `scan_area()` — returns detailed enemy data for all lanes
- `send_message(...)` — primary output is communication, not game actions

**Commander tools:**
- `send_message(...)` — primary output is directives and strategy
- `request_report(from: str)` — asks a specific agent to report on next cycle
- `no_action()` — Commander has no direct game actions, only communication

**Builder tools:**
- `place_turret(type: str, x: int, y: int)` — build a turret
- `upgrade_turret(x: int, y: int)` — upgrade existing turret
- `sell_turret(x: int, y: int)` — sell for partial refund
- `wait()` — do nothing this cycle
- `send_message(...)` — communicate back to Commander or broadcast status

- Handle rate limits: if API returns 429, agent sleeps and retries
- Handle timeouts: if LLM call takes > 15s, cancel and skip turn

### Task 3.5 — Context Window Management
- Agents accumulate history. Left unchecked, prompts grow unbounded.
- Rolling window: keep only last N messages and last M turns of action history
- Summarization: every 20 ticks, summarize older history into a compact "story so far" block
- Token budget: hard cap per agent per call (e.g., Scout: 1500 tokens, Commander: 2500, Builder: 2000)

---

## Phase 4: Communication Dynamics

> Goal: Make the async communication interesting and consequential. The hybrid messaging protocol (broadcast / direct / urgent) is the backbone — this phase defines the rules and constraints around it.

### Task 4.1 — Information Asymmetry
- Scout sees enemy details (type, HP, speed, exact position) — others don't
- Commander sees resource projections and wave schedule — others don't
- Builder sees exact build costs and valid positions — others don't
- No agent sees everything. They MUST communicate to coordinate effectively.
- Agents can only act on information they've received through their inbox — there is no omniscient state view

### Task 4.2 — Message Routing Expectations
Each agent's system prompt instructs it on when to use each message type:

**Scout:**
- `broadcast` — general threat reports ("3 enemies on north lane")
- `urgent` — imminent base threat ("tank 2 tiles from base, north lane")
- `direct` to Commander — strategic observations ("north lane is undefended, recommend turret")
- Should NOT send direct messages to Builder (that's the Commander's job — chain of command)

**Commander:**
- `broadcast` — high-level strategy shifts ("switching to defensive posture, save resources")
- `direct` to Builder — specific build orders ("place splash turret at (5,3)")
- `direct` to Scout — request for information ("report on south lane status")
- `urgent` — rarely, only for emergency pivots ("abandon south, everything to north NOW")

**Builder:**
- `broadcast` — resource status updates ("200 gold remaining, can afford 2 basic turrets")
- `direct` to Commander — pushback or clarification ("can't build sniper at (5,3), tile occupied, suggest (5,4)?")
- Should NOT send urgent messages (Builder doesn't have threat visibility)

These aren't hard rules — the LLM can break protocol if it reasons it should. But the prompt guides default behavior. Watching an agent break protocol in a crisis is part of what makes it interesting to demo.

### Task 4.3 — Stale Information Handling
- Every message in the inbox carries its `tick` timestamp
- When building an agent's prompt, annotate message age: "[5 ticks ago] Scout: 3 grunts on north lane"
- If a message is older than a configurable threshold (e.g., 8 ticks), append a warning: "(⚠ stale — situation may have changed)"
- Agents must reason about whether to trust old information or request a fresh report
- This is where async timing creates genuine decision-making tension

### Task 4.4 — Urgency Mechanism
- Scout marks messages as `urgent` when enemies are within N tiles of the base
- Urgent messages trigger `urgent_event.set()` on the message bus
- Sleeping agents (Commander, Builder) wake immediately via `asyncio.wait_for`
- On urgent wake, agents receive a shortened prompt focused on the urgent message: "URGENT from Scout: [content]. Respond immediately."
- After handling, agents resume their normal think interval
- Rate limit urgency: max 1 urgent message per 5 ticks to prevent spam

### Task 4.5 — Communication Breakdown Scenarios (configurable)
These are toggleable settings for testing and demoing agent robustness:
- **Message delay**: randomly delay delivery of messages by 1-5 ticks
- **Message drop**: randomly drop 10-20% of non-urgent messages (simulates unreliable channel)
- **Agent silence**: disable one agent's outbound messages entirely (Commander goes silent — does Builder improvise?)
- **Channel flood**: inject noise messages into inboxes to test agent signal filtering
- Purpose: demonstrate graceful degradation. The contrast between "agents with clean comms" vs "agents with degraded comms" is the strongest demo moment.

### Task 4.6 — Communication Metrics Tracking
Track per game for the post-game dashboard:
- Messages sent per agent, by type (broadcast / direct / urgent)
- Message read latency: how many ticks between send and the recipient actually reading it
- Stale reads: how many times an agent acted on a message older than threshold
- Urgent response time: ticks between urgent message and recipient's next action
- Protocol violations: did an agent send a message type it shouldn't have (e.g., Builder sending urgent)
- Unanswered directs: Commander sent a direct to Builder, but Builder never acknowledged

---

## Phase 5: Pygame Visualization

> Goal: Make it visually clear and demo-ready.

### Task 5.1 — Map Rendering
- Grid with colored tiles: brown for path, green for buildable, red for base, yellow for spawn
- Path lines connecting waypoints for clarity
- Lane labels (North, South, Center)

### Task 5.2 — Entity Rendering
- Enemies: colored circles by type (red=grunt, blue=tank, green=swarm), size proportional to HP
- Turrets: distinct shapes per type (circle=basic, triangle=splash, diamond=sniper)
- Range rings: show turret range on hover or as faint circles
- Projectile lines: brief flash from turret to target when firing

### Task 5.3 — Agent Activity Panel (right sidebar)
- Three rows, one per agent (Scout, Commander, Builder)
- Each row shows:
  - Agent name and role icon
  - Status: "Thinking..." / "Acting" / "Sleeping (3s)"
  - Last action taken
  - Thinking frequency indicator

### Task 5.4 — Message Feed (bottom panel or left sidebar)
- Scrolling chat log of agent messages
- Color-coded by sender: Scout=yellow, Commander=blue, Builder=green
- Message type indicators:
  - `broadcast` — normal text, no prefix
  - `direct` — prefixed with "→ [recipient]:" and slightly indented
  - `urgent` — red background highlight, bold text, exclamation icon
- Timestamp (game tick) on each message
- Stale messages (> threshold) shown with reduced opacity
- Direct messages only visible if addressed to an agent the viewer is "following" (or show all in debug mode)
- This is the most important visual element — it shows the agents coordinating, disagreeing, and adapting

### Task 5.5 — HUD
- Base HP bar (top)
- Resources counter
- Wave progress (e.g., "Wave 3/10")
- Game speed controls: pause, 1x, 2x, 4x (adjusts tick interval)
- Tick counter

---

## Phase 6: Polish & Portfolio Presentation

> Goal: Make it recruiter/interviewer ready.

### Task 6.1 — Logging & Replay
- Log every tick: game state snapshot, all agent prompts, LLM responses, actions taken, messages sent
- Save as structured JSON per game
- Replay mode: load a JSON log, step through tick-by-tick with full visualization
- Highlight moments where async timing caused interesting behavior (agent acted on stale info, urgency interrupt fired, builder improvised without commander input)

### Task 6.2 — Metrics Dashboard (post-game screen)
- Base HP remaining
- Total resources spent / earned
- Turrets placed / upgraded / sold
- Messages sent per agent
- Average response time per agent
- Stale info incidents: how many times an agent acted on info > 5 ticks old
- API cost breakdown per agent

### Task 6.3 — Interesting Failure Modes to Demo
- Run a game with communication delay cranked up — show agents failing to coordinate
- Run a game with the Commander disabled — show Builder improvising alone
- Run a game with all agents — show smooth coordination
- The contrast between these runs IS the demo

### Task 6.4 — README & Documentation
- Architecture diagram (the one at the top of this doc, polished)
- "Why async?" section explaining what sync can't do
- Setup and run instructions
- Example game replay GIF/video
- Design decisions: why these 3 roles, why these think intervals, how communication works
- Cost analysis: how much a typical 10-wave game costs in API calls
- Links to relevant research (multi-agent coordination, async decision-making)

---

## Milestones

| Milestone | Phases | What You Can Demo |
|-----------|--------|-------------------|
| M1 — Manual TD | Phase 1 | Click-to-place tower defense game, fully playable |
| M2 — Async infra | Phase 2 | Dummy agents running concurrently, messages flowing, no crashes |
| M3 — LLM agents | Phase 3 | Real agents playing the game, making decisions, communicating |
| M4 — Async dynamics | Phase 4 | Stale info, urgency interrupts, communication breakdown scenarios |
| M5 — Visual polish | Phase 5 | Full Pygame UI with agent panel, message feed, HUD |
| M6 — Portfolio ready | Phase 6 | Replays, metrics, failure mode demos, documentation |

---

## Technical Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM latency too high for real-time feel | Game feels sluggish | Agents think independently — game ticks don't wait for LLM. Visual shows "thinking..." state. Adjust think intervals. Add starter turrets so base isn't defenseless during first few seconds. |
| Agents produce invalid actions | Turret placed on invalid tile, etc. | Validation in `game_state.apply()`. Return error, agent retries next cycle. |
| Context window overflow | Prompts get too large over long games | Rolling window + summarization. Hard token caps per agent. |
| Pygame + asyncio thread conflict | Crashes or freezes | Pygame on main thread, asyncio on daemon thread. Communicate via thread-safe queue. Well-documented pattern. |
| API costs during development | Expensive iteration | Dummy agents for Phase 1-2 (zero cost). Record/replay mode for Phase 3+. Prompt caching cuts live costs by ~50%. Total dev cost estimated at $10-20. See API Cost Management section. |
| API rate limits hit during gameplay | Agent goes silent for several seconds | Exponential backoff with max 3 retries. Agent skips turn on failure — game continues. ~53 RPM is well within even low-tier limits. See Task A.3. |
| Agents don't coordinate well | Game is lost every time | Tune system prompts. Add few-shot examples of good coordination. Adjust think intervals. Simplify early waves. |
| Cold start — base undefended while agents boot | Lose HP in first few seconds | Pre-place 1-2 starter turrets per map. First wave is intentionally weak and slow. |

## API Cost Management & Prompt Caching Strategy

> Goal: Keep API costs predictable during development and low in production, while avoiding rate limit issues.

### Cost Projection

A typical 10-wave game (~5 minutes) generates approximately:
- Scout: ~150 calls (every ~2s)
- Builder: ~75 calls (every ~4s)
- Commander: ~38 calls (every ~8s)
- **Total: ~263 API calls per game**

Per-call token estimates (before caching):
| Agent     | Input tokens | Output tokens | Model          |
|-----------|-------------|---------------|----------------|
| Scout     | ~1,200      | ~150          | Haiku 4.5      |
| Builder   | ~1,500      | ~200          | Haiku 4.5      |
| Commander | ~2,000      | ~300          | Sonnet 4.6     |

**Estimated cost per game without caching:** ~$0.15–0.25
**Estimated cost per game with caching:** ~$0.05–0.10

### Task A.1 — Prompt Caching

Each agent's prompt has two parts:
1. **Static prefix** — system prompt, role description, game rules, tool definitions. Identical every call.
2. **Dynamic suffix** — current game state, recent messages, action history. Changes every call.

Use Anthropic's prompt caching to cache the static prefix:

```python
response = await client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    system=[
        {
            "type": "text",
            "text": SCOUT_SYSTEM_PROMPT,  # ~800 tokens, same every call
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[
        {
            "role": "user",
            "content": dynamic_game_state  # ~400 tokens, changes every call
        }
    ]
)
```

Cache hits cost 10% of standard input price. Since the system prompt is ~60-70% of the total input tokens for most calls, this cuts input costs by roughly 50-60%.

Cache TTL is 5 minutes by default — easily covers an entire game session without re-caching.

### Task A.2 — Model Tiering

Not all agents need the same model:

| Agent     | Model        | Rationale                                                |
|-----------|-------------|----------------------------------------------------------|
| Scout     | Haiku 4.5   | Simple pattern recognition: see enemies, report them. Fast response critical. |
| Builder   | Haiku 4.5   | Tactical execution: place turret at location. Needs to be responsive. |
| Commander | Sonnet 4.6  | Strategic reasoning: prioritize lanes, allocate resources, plan ahead. Slower is fine — thinks less often anyway. |

This keeps ~85% of calls (Scout + Builder) on the cheapest, fastest model.

**Fallback:** If Sonnet latency is too high for Commander (>5s regularly), drop to Haiku for all agents and compensate with richer system prompts and few-shot examples.

### Task A.3 — Rate Limit Handling

Expected request rate: ~53 requests/minute across all agents. Even the lowest API tier should handle this comfortably since requests are spread across time, not bursted.

However, implement defensive backoff:

```python
async def call_llm_with_backoff(client, **kwargs):
    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            response = await client.messages.create(**kwargs)
            return response
        except anthropic.RateLimitError:
            delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s
            logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1})")
            await asyncio.sleep(delay)
        except anthropic.APITimeoutError:
            logger.warning(f"API timeout, skipping turn")
            return None

    logger.error("Max retries exceeded, skipping turn")
    return None
```

Key behaviors:
- On 429 (rate limit): exponential backoff, retry up to 3 times
- On timeout: skip the turn entirely, agent acts on next cycle
- Never block the game loop — a failed API call just means that agent is temporarily inactive
- Log all failures for the post-game metrics dashboard

### Task A.4 — Development Mode (Mock/Cached Responses)

During development, most iteration is on game engine, renderer, and async infrastructure — not on agent behavior. Burning API calls for every test run is wasteful.

**Recording mode:**
```python
# Record LLM responses during a real game
if config.RECORD_MODE:
    response = await call_llm_with_backoff(client, **kwargs)
    save_to_cache(prompt_hash, response)
    return response
```

**Replay mode:**
```python
# Replay cached responses — no API calls
if config.REPLAY_MODE:
    cached = load_from_cache(prompt_hash)
    if cached:
        await asyncio.sleep(0.5)  # simulate latency
        return cached
    # Cache miss — fall through to real API call
```

**Dummy mode (Phase 2):**
- No API calls at all
- Agents return hardcoded or random valid actions
- Used for testing async infrastructure, message bus, game loop, renderer
- Zero cost

**Recommended dev workflow:**
1. Phase 1-2: Dummy mode only. Zero API cost.
2. Phase 3: Record a few real games, then iterate on prompts using replay mode. ~$1-2 total.
3. Phase 4-5: Mix of replay and live calls. ~$5-10 total.
4. Phase 6: Live calls for final demo recordings. ~$2-5 total.
5. **Total development cost estimate: $10-20**

### Task A.5 — Runtime Cost Tracking

Track token usage and cost in real time during a game:

```python
@dataclass
class AgentCostTracker:
    role: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_calls: int = 0
    failed_calls: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        # Calculate based on model pricing and cache hit rate
        ...
```

Display in the post-game metrics dashboard:
- Per-agent: total calls, tokens consumed, cache hit rate, estimated cost
- Per-game: total cost, cost per wave, cost per minute
- Useful for the portfolio README: "A typical 10-wave game costs $0.08 with prompt caching enabled"

---

- **Model choice**: Claude Haiku for Scout (fast, cheap), Claude Sonnet for Commander (better reasoning), Haiku for Builder. Or uniform model for simplicity.
- **Think intervals**: Start with Scout=2s, Builder=4s, Commander=8s. Tune based on LLM latency.
- **Map complexity**: Start with 2 lanes, expand to 3 if agents handle it.
- **Wave count**: 8-10 waves, ~5 minutes total game time. Long enough to demo, short enough to iterate.
- **Turret upgrade system**: Keep it simple — one upgrade level per turret, increases damage and range. Don't over-scope.
