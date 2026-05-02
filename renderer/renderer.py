"""Pygame renderer matching the reference UI style.

Layout:
  - Top HUD bar: Base HP, Tick, Resources, Wave, speed controls
  - Left: game map with grid, lanes, enemies, turrets
  - Right sidebar: Agent Activity Panel (3 agent cards)
  - Bottom: Message Feed (scrolling log)
"""

from __future__ import annotations
import math
import pygame
from game.state import GameState, StateSnapshot, Action
from config import (
    Config, TILE_GROUND, TILE_PATH, TILE_BASE, TILE_SPAWN,
    TURRET_TYPES,
)

# --- Color Palette (dark theme matching reference) ---
BG_COLOR = (30, 32, 38)
HUD_BG = (38, 40, 48)
PANEL_BG = (35, 38, 46)
PANEL_BORDER = (58, 62, 74)
FONT_COLOR = (220, 222, 228)
FONT_DIM = (140, 144, 156)
FONT_BRIGHT = (255, 255, 255)

# Map tile colors (reference style: green ground, brown paths)
TILE_COLORS = {
    TILE_GROUND: (76, 135, 68),
    TILE_PATH: (140, 108, 66),
    TILE_BASE: (190, 45, 45),
    TILE_SPAWN: (190, 170, 50),
}
GRID_LINE_COLOR = (66, 115, 58)
PATH_BORDER_COLOR = (110, 82, 48)

# Agent colors
SCOUT_COLOR = (240, 200, 50)
COMMANDER_COLOR = (80, 140, 240)
BUILDER_COLOR = (60, 200, 100)

# HUD element colors
HP_GREEN = (80, 200, 80)
HP_YELLOW = (220, 180, 40)
HP_RED = (210, 50, 50)
GOLD_COLOR = (255, 210, 50)
TICK_COLOR = (220, 140, 40)

SPEED_BTN_BG = (50, 54, 64)
SPEED_BTN_ACTIVE = (80, 90, 120)
SPEED_BTN_BORDER = (90, 95, 110)


class PygameRenderer:
    def __init__(self, game_state: GameState, message_bus, config: Config):
        self.game_state = game_state
        self.message_bus = message_bus
        self.config = config
        self.selected_turret_type = "basic"
        self.hovered_tile: tuple[int, int] | None = None
        self.show_ranges = False
        self.paused = False
        self.speed_index = 1  # 0=pause, 1=1x, 2=2x, 3=4x
        self.speed_values = [0, 1.0, 2.0, 4.0]
        self.speed_labels = ["||", "1x", "2x", "4x"]
        self.message_log: list[dict] = []

        pygame.init()

        # Layout calculations
        self.screen_w = config.screen_width
        self.screen_h = config.screen_height
        self.hud_h = 56
        self.sidebar_w = 260
        self.msgfeed_h = 150
        self.map_padding = 12

        map_area_w = self.screen_w - self.sidebar_w - self.map_padding * 3
        map_area_h = self.screen_h - self.hud_h - self.msgfeed_h - self.map_padding * 3
        self.tile_size = min(
            map_area_w // config.grid_width,
            map_area_h // config.grid_height,
        )
        self.map_pixel_w = self.tile_size * config.grid_width
        self.map_pixel_h = self.tile_size * config.grid_height
        self.map_x = self.map_padding
        self.map_y = self.hud_h + self.map_padding
        self.sidebar_x = self.map_x + self.map_pixel_w + self.map_padding
        self.sidebar_y = self.hud_h + self.map_padding
        self.sidebar_h = self.map_pixel_h
        self.msgfeed_x = self.map_padding
        self.msgfeed_y = self.map_y + self.map_pixel_h + self.map_padding
        self.msgfeed_w = self.screen_w - self.map_padding * 2
        self.msgfeed_real_h = self.screen_h - self.msgfeed_y - self.map_padding

        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h))
        pygame.display.set_caption("Async Multi-Agent Tower Defense")
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("dejavusansmono", 15)
        self.font_bold = pygame.font.SysFont("dejavusansmono", 15, bold=True)
        self.font_large = pygame.font.SysFont("dejavusansmono", 18, bold=True)
        self.font_small = pygame.font.SysFont("dejavusansmono", 12)
        self.font_title = pygame.font.SysFont("dejavusansmono", 16, bold=True)
        self.font_hud = pygame.font.SysFont("dejavusansmono", 14, bold=True)
        self.font_lane = pygame.font.SysFont("dejavusansmono", 11, bold=True)

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                self._handle_event(event)

            snap = self.game_state.snapshot()
            self.screen.fill(BG_COLOR)
            self._draw_hud(snap)
            self._draw_map(snap)
            self._draw_enemies(snap)
            self._draw_turrets(snap)
            self._draw_projectiles(snap)
            self._draw_hover(snap)
            self._draw_agent_panel(snap)
            self._draw_message_feed(snap)
            self._draw_game_over(snap)
            pygame.display.flip()
            self.clock.tick(60)

    # --- Event Handling ---

    def _handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self._handle_speed_click(event.pos):
                    return
                self._handle_click(event.pos)
            elif event.button == 3:
                self._handle_right_click(event.pos)
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event.key)

    def _update_hover(self, pos):
        gx, gy = self._screen_to_grid(pos)
        if gx is not None:
            self.hovered_tile = (gx, gy)
        else:
            self.hovered_tile = None

    def _handle_click(self, pos):
        gx, gy = self._screen_to_grid(pos)
        if gx is None:
            return
        existing = self.game_state.get_turret_at(gx, gy)
        if existing:
            ok, msg = self.game_state.apply(Action("upgrade_turret", x=gx, y=gy))
            if ok:
                self._log_msg("Builder", f"Upgraded turret at ({gx},{gy})", BUILDER_COLOR)
        else:
            ok, msg = self.game_state.apply(Action("place_turret", self.selected_turret_type, gx, gy))
            if ok:
                self._log_msg("Builder", f"Placed {self.selected_turret_type} at ({gx},{gy})", BUILDER_COLOR)

    def _handle_right_click(self, pos):
        gx, gy = self._screen_to_grid(pos)
        if gx is None:
            return
        ok, msg = self.game_state.apply(Action("sell_turret", x=gx, y=gy))
        if ok:
            self._log_msg("Builder", f"Sold turret at ({gx},{gy})", BUILDER_COLOR)

    def _handle_key(self, key):
        if key == pygame.K_1:
            self.selected_turret_type = "basic"
        elif key == pygame.K_2:
            self.selected_turret_type = "splash"
        elif key == pygame.K_3:
            self.selected_turret_type = "sniper"
        elif key == pygame.K_r:
            self.show_ranges = not self.show_ranges
        elif key == pygame.K_SPACE:
            if self.speed_index == 0:
                self.speed_index = 1
            else:
                self.speed_index = 0
            self._apply_speed()

    def _handle_speed_click(self, pos) -> bool:
        btn_y = 14
        btn_size = 28
        btn_gap = 4
        start_x = self.screen_w - (btn_size + btn_gap) * 4 - 10
        for i in range(4):
            bx = start_x + i * (btn_size + btn_gap)
            if bx <= pos[0] <= bx + btn_size and btn_y <= pos[1] <= btn_y + btn_size:
                self.speed_index = i
                self._apply_speed()
                return True
        return False

    def _apply_speed(self):
        spd = self.speed_values[self.speed_index]
        if spd == 0:
            self.paused = True
            self.game_state.running = False
        else:
            self.paused = False
            self.game_state.running = True
            self.config.speed_multiplier = spd

    def _log_msg(self, sender: str, content: str, color: tuple):
        tick = self.game_state.tick
        self.message_log.append({"tick": tick, "sender": sender, "content": content, "color": color})
        if len(self.message_log) > 100:
            self.message_log = self.message_log[-100:]

    # --- Coordinate Helpers ---

    def _screen_to_grid(self, pos) -> tuple[int | None, int | None]:
        mx, my = pos
        gx = (mx - self.map_x) // self.tile_size
        gy = (my - self.map_y) // self.tile_size
        gmap = self.game_state.game_map
        if 0 <= gx < gmap.width and 0 <= gy < gmap.height:
            return gx, gy
        return None, None

    def _grid_to_screen(self, gx: float, gy: float) -> tuple[int, int]:
        return (
            int(self.map_x + gx * self.tile_size),
            int(self.map_y + gy * self.tile_size),
        )

    def _grid_center(self, gx: float, gy: float) -> tuple[int, int]:
        sx, sy = self._grid_to_screen(gx, gy)
        return sx + self.tile_size // 2, sy + self.tile_size // 2

    # --- Drawing: HUD ---

    def _draw_hud(self, snap: StateSnapshot):
        pygame.draw.rect(self.screen, HUD_BG, (0, 0, self.screen_w, self.hud_h))
        pygame.draw.line(self.screen, PANEL_BORDER, (0, self.hud_h - 1), (self.screen_w, self.hud_h - 1))

        x_cursor = 16
        y_row1 = 10
        y_row2 = 30

        # Base HP label + bar
        hp_label = self.font_hud.render("Base HP", True, FONT_COLOR)
        self.screen.blit(hp_label, (x_cursor, y_row1))
        hp_ratio = max(0, snap.base_hp / self.config.base_hp)
        bar_x = x_cursor + hp_label.get_width() + 8
        bar_w = 120
        bar_h = 12
        pygame.draw.rect(self.screen, (50, 20, 20), (bar_x, y_row1 + 2, bar_w, bar_h), border_radius=3)
        hp_color = HP_GREEN if hp_ratio > 0.5 else HP_YELLOW if hp_ratio > 0.25 else HP_RED
        if hp_ratio > 0:
            pygame.draw.rect(self.screen, hp_color, (bar_x, y_row1 + 2, int(bar_w * hp_ratio), bar_h), border_radius=3)

        # Tick label + bar
        tick_label = self.font_hud.render(f"Tick: {snap.tick}", True, FONT_COLOR)
        self.screen.blit(tick_label, (x_cursor, y_row2))
        tick_bar_x = x_cursor + tick_label.get_width() + 8
        tick_bar_w = 60
        tick_ratio = min(1.0, (snap.tick % 100) / 100.0)
        pygame.draw.rect(self.screen, (50, 30, 15), (tick_bar_x, y_row2 + 2, tick_bar_w, bar_h), border_radius=3)
        if tick_ratio > 0:
            pygame.draw.rect(self.screen, TICK_COLOR, (tick_bar_x, y_row2 + 2, int(tick_bar_w * tick_ratio), bar_h), border_radius=3)

        # Resources (centered area)
        res_x = self.screen_w // 2 - 80
        res_text = self.font_large.render(f"Resources: {snap.resources}$", True, GOLD_COLOR)
        self.screen.blit(res_text, (res_x, y_row1))

        # Wave (centered area, row 2)
        wave_text = self.font_hud.render(f"Wave: {snap.current_wave}/{snap.total_waves}", True, FONT_COLOR)
        self.screen.blit(wave_text, (res_x + 30, y_row2))

        # Speed buttons (right side)
        btn_size = 28
        btn_gap = 4
        start_x = self.screen_w - (btn_size + btn_gap) * 4 - 10
        btn_y = 14
        for i, label in enumerate(self.speed_labels):
            bx = start_x + i * (btn_size + btn_gap)
            bg = SPEED_BTN_ACTIVE if i == self.speed_index else SPEED_BTN_BG
            pygame.draw.rect(self.screen, bg, (bx, btn_y, btn_size, btn_size), border_radius=4)
            pygame.draw.rect(self.screen, SPEED_BTN_BORDER, (bx, btn_y, btn_size, btn_size), 1, border_radius=4)
            lbl = self.font_small.render(label, True, FONT_BRIGHT if i == self.speed_index else FONT_DIM)
            lbl_rect = lbl.get_rect(center=(bx + btn_size // 2, btn_y + btn_size // 2))
            self.screen.blit(lbl, lbl_rect)

    # --- Drawing: Map ---

    def _draw_map(self, snap: StateSnapshot):
        gmap = snap.game_map
        ts = self.tile_size

        # Map background border
        pygame.draw.rect(self.screen, PANEL_BORDER,
                         (self.map_x - 2, self.map_y - 2, self.map_pixel_w + 4, self.map_pixel_h + 4),
                         2, border_radius=4)

        for y in range(gmap.height):
            for x in range(gmap.width):
                tile = gmap.grid[y][x]
                color = TILE_COLORS.get(tile, (50, 50, 50))
                sx, sy = self._grid_to_screen(x, y)
                pygame.draw.rect(self.screen, color, (sx, sy, ts, ts))

                # Grid lines on ground tiles
                if tile == TILE_GROUND:
                    pygame.draw.rect(self.screen, GRID_LINE_COLOR, (sx, sy, ts, ts), 1)

                # Path border effect
                if tile == TILE_PATH:
                    pygame.draw.rect(self.screen, PATH_BORDER_COLOR, (sx, sy, ts, ts), 1)

                # Base label
                if tile == TILE_BASE:
                    base_lbl = self.font_bold.render("Base", True, FONT_BRIGHT)
                    lbl_rect = base_lbl.get_rect(center=(sx + ts // 2, sy + ts // 2))
                    self.screen.blit(base_lbl, lbl_rect)

        # Lane labels along the path
        for lane in gmap.lanes:
            if len(lane.waypoints) > 4:
                wp = lane.waypoints[3]
                sx, sy = self._grid_to_screen(*wp)
                label = self.font_lane.render(f"{lane.name} Lane", True, (255, 255, 255, 180))
                self.screen.blit(label, (sx + 2, sy + ts - 12))

    # --- Drawing: Enemies ---

    def _draw_enemies(self, snap: StateSnapshot):
        ts = self.tile_size
        for enemy in snap.enemies:
            if not enemy.alive:
                continue
            cx, cy = self._grid_center(enemy.x, enemy.y)
            max_radius = ts // 3
            radius = max(4, int(max_radius * 0.6 + max_radius * 0.4 * (enemy.hp / enemy.max_hp)))

            # Outer glow
            glow_surf = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
            glow_color = (*enemy.color, 40)
            pygame.draw.circle(glow_surf, glow_color, (radius * 2, radius * 2), radius + 3)
            self.screen.blit(glow_surf, (cx - radius * 2, cy - radius * 2))

            # Main circle
            pygame.draw.circle(self.screen, enemy.color, (cx, cy), radius)
            # Inner highlight
            highlight = tuple(min(255, c + 60) for c in enemy.color)
            pygame.draw.circle(self.screen, highlight, (cx - radius // 4, cy - radius // 4), max(2, radius // 3))

            # HP bar
            bar_w = ts - 6
            bar_h = 3
            hp_ratio = enemy.hp / enemy.max_hp
            bx = cx - bar_w // 2
            by = cy - radius - 6
            pygame.draw.rect(self.screen, (40, 15, 15), (bx, by, bar_w, bar_h), border_radius=1)
            if hp_ratio > 0:
                bar_color = HP_GREEN if hp_ratio > 0.5 else HP_YELLOW if hp_ratio > 0.25 else HP_RED
                pygame.draw.rect(self.screen, bar_color, (bx, by, max(1, int(bar_w * hp_ratio)), bar_h), border_radius=1)

    # --- Drawing: Turrets ---

    def _draw_turrets(self, snap: StateSnapshot):
        ts = self.tile_size
        for turret in snap.turrets:
            sx, sy = self._grid_to_screen(turret.x, turret.y)
            cx, cy = sx + ts // 2, sy + ts // 2

            # Dark square base
            base_margin = 3
            pygame.draw.rect(self.screen, (30, 35, 30),
                             (sx + base_margin, sy + base_margin,
                              ts - base_margin * 2, ts - base_margin * 2),
                             border_radius=4)
            pygame.draw.rect(self.screen, (50, 55, 50),
                             (sx + base_margin, sy + base_margin,
                              ts - base_margin * 2, ts - base_margin * 2),
                             1, border_radius=4)

            # Range ring
            if self.show_ranges:
                range_px = int(turret.range * ts)
                range_surf = pygame.Surface((range_px * 2, range_px * 2), pygame.SRCALPHA)
                pygame.draw.circle(range_surf, (150, 220, 255, 25), (range_px, range_px), range_px)
                pygame.draw.circle(range_surf, (150, 220, 255, 50), (range_px, range_px), range_px, 1)
                self.screen.blit(range_surf, (cx - range_px, cy - range_px))

            # Turret shape
            size = ts // 3
            if turret.turret_type == "basic":
                pygame.draw.circle(self.screen, turret.color, (cx, cy), size)
                pygame.draw.circle(self.screen, tuple(min(255, c + 40) for c in turret.color), (cx, cy), size, 2)
            elif turret.turret_type == "splash":
                pts = [
                    (cx, cy - size),
                    (cx - size, cy + size),
                    (cx + size, cy + size),
                ]
                pygame.draw.polygon(self.screen, turret.color, pts)
                pygame.draw.polygon(self.screen, tuple(min(255, c + 40) for c in turret.color), pts, 2)
            elif turret.turret_type == "sniper":
                pts = [
                    (cx, cy - size),
                    (cx + size, cy),
                    (cx, cy + size),
                    (cx - size, cy),
                ]
                pygame.draw.polygon(self.screen, turret.color, pts)
                pygame.draw.polygon(self.screen, tuple(min(255, c + 40) for c in turret.color), pts, 2)

            # Level star
            if turret.level > 1:
                star = self.font_small.render("*", True, (255, 255, 100))
                self.screen.blit(star, (sx + base_margin + 1, sy + base_margin))

    # --- Drawing: Projectiles ---

    def _draw_projectiles(self, snap: StateSnapshot):
        for (tx, ty), (ex, ey) in snap.recent_hits:
            start = self._grid_center(tx, ty)
            end = self._grid_center(ex, ey)
            pygame.draw.line(self.screen, (255, 80, 60), start, end, 2)
            # Impact flash
            pygame.draw.circle(self.screen, (255, 200, 80), end, 4)

    # --- Drawing: Hover & Tooltip ---

    def _draw_hover(self, snap: StateSnapshot):
        if self.hovered_tile is None:
            return
        gx, gy = self.hovered_tile
        sx, sy = self._grid_to_screen(gx, gy)
        ts = self.tile_size

        hover_surf = pygame.Surface((ts, ts), pygame.SRCALPHA)
        existing = None
        for t in snap.turrets:
            if t.x == gx and t.y == gy:
                existing = t
                break

        if snap.game_map.is_buildable(gx, gy):
            if existing:
                pygame.draw.rect(hover_surf, (100, 200, 255, 50), (0, 0, ts, ts))
            else:
                pygame.draw.rect(hover_surf, (100, 255, 100, 50), (0, 0, ts, ts))
                # Range preview
                r = TURRET_TYPES[self.selected_turret_type]["range"]
                range_px = int(r * ts)
                ccx, ccy = sx + ts // 2, sy + ts // 2
                range_surf = pygame.Surface((range_px * 2, range_px * 2), pygame.SRCALPHA)
                pygame.draw.circle(range_surf, (200, 220, 255, 20), (range_px, range_px), range_px)
                pygame.draw.circle(range_surf, (200, 220, 255, 60), (range_px, range_px), range_px, 1)
                self.screen.blit(range_surf, (ccx - range_px, ccy - range_px))
        else:
            pygame.draw.rect(hover_surf, (255, 60, 60, 40), (0, 0, ts, ts))
        self.screen.blit(hover_surf, (sx, sy))
        pygame.draw.rect(self.screen, (255, 255, 255, 80), (sx, sy, ts, ts), 1)

        # Tooltip
        tooltip_lines = [f"({gx}, {gy})"]
        if existing:
            tooltip_lines.append(f"{existing.turret_type.title()} Lv{existing.level}")
            tooltip_lines.append(f"DMG: {existing.damage:.0f}  RNG: {existing.range:.1f}")
            if existing.can_upgrade():
                tooltip_lines.append(f"Click to upgrade: ${existing.upgrade_cost()}")
            tooltip_lines.append(f"Right-click sell: ${existing.sell_value}")
        elif snap.game_map.tile_at(gx, gy) == TILE_GROUND:
            cost = TURRET_TYPES[self.selected_turret_type]["cost"]
            tooltip_lines.append(f"Build {self.selected_turret_type.title()}: ${cost}")
        if len(tooltip_lines) > 1:
            self._draw_tooltip(sx + ts + 4, sy, tooltip_lines)

    def _draw_tooltip(self, x: int, y: int, lines: list[str]):
        padding = 6
        line_h = 16
        max_w = max(self.font_small.size(l)[0] for l in lines) + padding * 2
        total_h = len(lines) * line_h + padding * 2
        if x + max_w > self.sidebar_x - 4:
            x = x - max_w - self.tile_size - 8
        if y + total_h > self.map_y + self.map_pixel_h:
            y = self.map_y + self.map_pixel_h - total_h
        pygame.draw.rect(self.screen, (22, 24, 30), (x, y, max_w, total_h), border_radius=4)
        pygame.draw.rect(self.screen, PANEL_BORDER, (x, y, max_w, total_h), 1, border_radius=4)
        for i, line in enumerate(lines):
            color = FONT_BRIGHT if i == 0 else FONT_COLOR
            text = self.font_small.render(line, True, color)
            self.screen.blit(text, (x + padding, y + padding + i * line_h))

    # --- Drawing: Agent Activity Panel (right sidebar) ---

    def _draw_agent_panel(self, snap: StateSnapshot):
        x = self.sidebar_x
        w = self.sidebar_w
        h = self.sidebar_h
        y = self.sidebar_y

        # Panel background
        pygame.draw.rect(self.screen, PANEL_BG, (x, y, w, h), border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, (x, y, w, h), 1, border_radius=6)

        # Title
        title = self.font_title.render("Agent Activity Panel", True, FONT_BRIGHT)
        self.screen.blit(title, (x + 12, y + 10))

        # Agent cards — live status from bus when available
        card_h = (h - 50) // 3 - 8
        if self.message_bus:
            s = self.message_bus.agent_statuses
            agents = [
                ("Scout Agent",     SCOUT_COLOR,     s["Scout"]["status"],     s["Scout"]["last_action"]),
                ("Commander Agent", COMMANDER_COLOR, s["Commander"]["status"], s["Commander"]["last_action"]),
                ("Builder Agent",   BUILDER_COLOR,   s["Builder"]["status"],   s["Builder"]["last_action"]),
            ]
        else:
            agents = [
                ("Scout Agent",     SCOUT_COLOR,     "Scanning...",  "Waiting for agents"),
                ("Commander Agent", COMMANDER_COLOR, "Idle",         "Waiting for agents"),
                ("Builder Agent",   BUILDER_COLOR,   "Manual Mode",  self._get_last_build_action()),
            ]

        for i, (name, color, status, last_action) in enumerate(agents):
            cy = y + 38 + i * (card_h + 8)
            self._draw_agent_card(x + 8, cy, w - 16, card_h, name, color, status, last_action)

    def _draw_agent_card(self, x, y, w, h, name, color, status, last_action):
        # Card background
        pygame.draw.rect(self.screen, (28, 30, 38), (x, y, w, h), border_radius=5)
        pygame.draw.rect(self.screen, (50, 54, 64), (x, y, w, h), 1, border_radius=5)

        # Color accent bar on left
        pygame.draw.rect(self.screen, color, (x, y + 4, 3, h - 8), border_radius=2)

        # Agent name
        name_surf = self.font_bold.render(name, True, FONT_BRIGHT)
        self.screen.blit(name_surf, (x + 12, y + 8))

        # Status
        status_label = self.font_small.render("Status: ", True, FONT_DIM)
        status_val = self.font_small.render(status, True, color)
        self.screen.blit(status_label, (x + 12, y + 28))
        self.screen.blit(status_val, (x + 12 + status_label.get_width(), y + 28))

        # Last action
        if last_action:
            action_label = self.font_small.render("Last: ", True, FONT_DIM)
            self.screen.blit(action_label, (x + 12, y + 46))
            max_action_w = w - 36 - action_label.get_width()
            action_text = last_action
            action_surf = self.font_small.render(action_text, True, FONT_COLOR)
            if action_surf.get_width() > max_action_w:
                while action_surf.get_width() > max_action_w and len(action_text) > 3:
                    action_text = action_text[:-4] + "..."
                    action_surf = self.font_small.render(action_text, True, FONT_COLOR)
            self.screen.blit(action_surf, (x + 12 + action_label.get_width(), y + 46))

        # Turret selection hints (manual mode only)
        if "Builder" in name and self.config.mode == "manual":
            sel_y = y + 66
            sel_label = self.font_small.render("Selected: ", True, FONT_DIM)
            self.screen.blit(sel_label, (x + 12, sel_y))
            sel_type = self.selected_turret_type.title()
            sel_cost = TURRET_TYPES[self.selected_turret_type]["cost"]
            sel_surf = self.font_small.render(f"{sel_type} (${sel_cost})", True, BUILDER_COLOR)
            self.screen.blit(sel_surf, (x + 12 + sel_label.get_width(), sel_y))
            hint_surf = self.font_small.render("1=Basic  2=Splash  3=Sniper", True, FONT_DIM)
            self.screen.blit(hint_surf, (x + 12, sel_y + 18))

    def _get_last_build_action(self) -> str:
        for msg in reversed(self.message_log):
            if msg["sender"] == "Builder":
                return msg["content"]
        return "None"

    # --- Drawing: Message Feed ---

    _AGENT_COLORS = {
        "Scout": SCOUT_COLOR,
        "Commander": COMMANDER_COLOR,
        "Builder": BUILDER_COLOR,
    }
    _URGENT_BG = (80, 20, 20)

    def _draw_message_feed(self, snap: StateSnapshot):
        x = self.msgfeed_x
        y = self.msgfeed_y
        w = self.msgfeed_w
        h = self.msgfeed_real_h

        # Panel background
        pygame.draw.rect(self.screen, PANEL_BG, (x, y, w, h), border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, (x, y, w, h), 1, border_radius=6)

        # Title
        title = self.font_title.render("Message Feed", True, FONT_BRIGHT)
        self.screen.blit(title, (x + 12, y + 8))

        # Build display list from bus (agent mode) or local log (manual mode)
        if self.message_bus:
            raw = self.message_bus.get_display_log()
            display = [
                {
                    "tick": m.tick,
                    "sender": m.sender,
                    "content": m.content,
                    "color": self._AGENT_COLORS.get(m.sender, FONT_COLOR),
                    "urgent": m.type == "urgent",
                }
                for m in raw
            ]
        else:
            display = [
                {**m, "urgent": False}
                for m in self.message_log
            ]

        if not display:
            empty = self.font_small.render("No messages yet.", True, FONT_DIM)
            self.screen.blit(empty, (x + 12, y + 30))
            return

        msg_y = y + 30
        line_h = 17
        max_lines = (h - 38) // line_h
        visible = display[-max_lines:]

        for msg in reversed(visible):
            if msg_y + line_h > y + h - 4:
                break
            color = msg["color"]

            # Urgent highlight row
            if msg.get("urgent"):
                pygame.draw.rect(self.screen, self._URGENT_BG,
                                 (x + 6, msg_y - 1, w - 12, line_h - 1), border_radius=2)

            tick_surf = self.font_small.render(f"T{msg['tick']:>3}", True, color)
            self.screen.blit(tick_surf, (x + 12, msg_y))

            sep_surf = self.font_small.render(" | ", True, FONT_DIM)
            self.screen.blit(sep_surf, (x + 12 + tick_surf.get_width(), msg_y))

            content_x = x + 12 + tick_surf.get_width() + sep_surf.get_width()
            sender_surf = self.font_small.render(f"{msg['sender']}: ", True, color)
            self.screen.blit(sender_surf, (content_x, msg_y))

            max_text_w = w - (content_x - x) - sender_surf.get_width() - 16
            text = msg["content"]
            text_surf = self.font_small.render(text, True, FONT_COLOR)
            while text_surf.get_width() > max_text_w and len(text) > 4:
                text = text[:-4] + "..."
                text_surf = self.font_small.render(text, True, FONT_COLOR)
            self.screen.blit(text_surf, (content_x + sender_surf.get_width(), msg_y))

            msg_y += line_h

    # --- Drawing: Game Over ---

    def _draw_game_over(self, snap: StateSnapshot):
        if snap.running:
            return
        overlay = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        if snap.won:
            msg = "VICTORY!"
            color = (50, 255, 80)
        else:
            msg = "DEFEAT"
            color = (255, 60, 60)

        text = pygame.font.SysFont("dejavusansmono", 48, bold=True).render(msg, True, color)
        rect = text.get_rect(center=(self.screen_w // 2, self.screen_h // 2 - 30))
        self.screen.blit(text, rect)

        sub = self.font_large.render(
            f"Wave {snap.current_wave}  |  Base HP: {snap.base_hp}  |  Tick: {snap.tick}",
            True, FONT_COLOR,
        )
        sub_rect = sub.get_rect(center=(self.screen_w // 2, self.screen_h // 2 + 20))
        self.screen.blit(sub, sub_rect)
