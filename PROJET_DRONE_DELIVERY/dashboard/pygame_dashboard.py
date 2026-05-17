"""
=============================================================================
DASHBOARD PYGAME — Visualisation Néon Cyberpunk ⚡
=============================================================================

DESIGN:
    Inspiré des HUDs de jeux futuristes (Cyberpunk 2077, Tron, Watch Dogs).
    Palette néon (cyan / magenta / vert acide) sur fond noir profond.
    Effets de glow, particules météo, animations fluides.

ELEMENTS VISUELS:
    • Grille de fond animée avec scan-line radar
    • Drones avec hélices rotatives + halo lumineux + arc de batterie
    • Stations de recharge avec pulsation électrique
    • Routes pickup→dropoff en pointillés animés
    • Particules météo dynamiques (pluie/vent/orage)
    • Panneau latéral moderne avec cards gradients
    • Mini-cartes drones individuelles avec barres animées

MODE DEMO:
    Si aucun agent ne se connecte dans les 6 secondes après le démarrage,
    on injecte des drones fictifs pour MONTRER le rendu — utile pour
    démontrer le visuel même sans le système SMA complet derrière.
=============================================================================
"""

import math
import random
import time

import pygame

from utils.world_state import world_state
from utils.ontologies import Config


# =============================================================================
# DIMENSIONS & PALETTE
# =============================================================================
GRID_W = Config.MAP_WIDTH       # 50
GRID_H = Config.MAP_HEIGHT      # 50
CELL = 16                       # 16 pixels par cellule
MAP_PX = GRID_W * CELL          # 800
PANEL_W = 480
WINDOW_W = MAP_PX + PANEL_W     # 1280
WINDOW_H = MAP_PX               # 800

# Palette néon cyberpunk
COLOR_BG = (6, 8, 16)
COLOR_GRID = (18, 26, 42)
COLOR_GRID_BRIGHT = (35, 50, 80)
COLOR_PANEL_BG_TOP = (12, 14, 24)
COLOR_PANEL_BG_BOT = (20, 22, 38)
COLOR_TEXT = (235, 240, 255)
COLOR_TEXT_DIM = (140, 150, 175)

NEON_CYAN = (0, 245, 255)
NEON_MAGENTA = (255, 60, 200)
NEON_GREEN = (60, 255, 130)
NEON_YELLOW = (255, 230, 60)
NEON_RED = (255, 70, 90)
NEON_ORANGE = (255, 150, 50)
NEON_PURPLE = (180, 100, 255)
NEON_BLUE = (80, 150, 255)

# Couleur des drones selon le statut
STATUS_COLOR = {
    "idle":              NEON_GREEN,
    "moving_to_pickup":  NEON_YELLOW,
    "carrying":          NEON_ORANGE,
    "moving_to_station": NEON_RED,
    "charging":          NEON_PURPLE,
}

STATUS_LABEL = {
    "idle":              "EN ATTENTE",
    "moving_to_pickup":  "VERS PICKUP",
    "carrying":          "LIVRAISON",
    "moving_to_station": "VERS STATION",
    "charging":          "RECHARGE",
}


# =============================================================================
# OUTILS DE RENDU
# =============================================================================

def grid_to_screen(pos):
    """Position grille → coordonnées pixel (centre de cellule)."""
    x, y = pos
    return (int(x * CELL + CELL // 2), int(y * CELL + CELL // 2))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def make_glow_surface(radius, color, intensity=4):
    """Pré-rendu d'un cercle avec effet glow néon (cache-friendly)."""
    size = radius * 6
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (size // 2, size // 2)
    for i in range(intensity, 0, -1):
        alpha = max(0, 60 - i * 12)
        pygame.draw.circle(
            surf, (*color, alpha), center, radius + i * 3
        )
    pygame.draw.circle(surf, (*color, 220), center, radius)
    pygame.draw.circle(surf, (255, 255, 255, 180), center, max(1, radius - 2), 1)
    return surf


# Cache des surfaces glow (très important pour les performances)
_glow_cache = {}


def blit_glow(target, color, pos, radius, intensity=4):
    """Blit un glow pré-rendu (utilisation du cache)."""
    key = (radius, color, intensity)
    if key not in _glow_cache:
        _glow_cache[key] = make_glow_surface(radius, color, intensity)
    surf = _glow_cache[key]
    rect = surf.get_rect(center=pos)
    target.blit(surf, rect, special_flags=pygame.BLEND_RGBA_ADD)


def draw_glow_text(surf, text, font, color, pos, glow_color=None):
    """Texte avec halo lumineux subtil."""
    glow_color = glow_color or color
    # Halo (4 passes décalées)
    glow_surf = font.render(text, True, glow_color)
    glow_surf.set_alpha(60)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        surf.blit(glow_surf, (pos[0] + dx, pos[1] + dy))
    # Texte principal
    text_surf = font.render(text, True, color)
    surf.blit(text_surf, pos)


# =============================================================================
# COMPOSANTS VISUELS
# =============================================================================

def draw_animated_grid(surf, tick):
    """Grille de fond avec lignes principales + scan line radar."""
    # Lignes fines toutes les cellules
    for x in range(0, MAP_PX + 1, CELL):
        pygame.draw.line(surf, COLOR_GRID, (x, 0), (x, MAP_PX), 1)
    for y in range(0, MAP_PX + 1, CELL):
        pygame.draw.line(surf, COLOR_GRID, (0, y), (MAP_PX, y), 1)

    # Lignes "fortes" tous les 5 cellules
    for x in range(0, MAP_PX + 1, CELL * 5):
        pygame.draw.line(surf, COLOR_GRID_BRIGHT, (x, 0), (x, MAP_PX), 1)
    for y in range(0, MAP_PX + 1, CELL * 5):
        pygame.draw.line(surf, COLOR_GRID_BRIGHT, (0, y), (MAP_PX, y), 1)

    # SCAN-LINE radar (effet horizontal qui défile lentement)
    scan_y = (tick * 1.5) % (MAP_PX + 120) - 60
    scan_height = 60
    scan_surf = pygame.Surface((MAP_PX, scan_height), pygame.SRCALPHA)
    for i in range(scan_height):
        # Gradient d'alpha du haut vers le bas
        alpha = int(35 * (1 - abs(i - scan_height // 2) / (scan_height // 2)))
        if alpha > 0:
            pygame.draw.line(scan_surf, (0, 245, 255, alpha),
                             (0, i), (MAP_PX, i))
    surf.blit(scan_surf, (0, int(scan_y)), special_flags=pygame.BLEND_RGBA_ADD)


def draw_weather_particles(surf, weather, tick):
    """Particules de météo animées sur la carte."""
    if weather in ("rainy", "stormy"):
        # Gouttes de pluie diagonales
        count = 150 if weather == "rainy" else 250
        color = (120, 170, 255) if weather == "rainy" else (170, 200, 255)
        length = 12 if weather == "rainy" else 22
        speed = 6 if weather == "rainy" else 12

        for i in range(count):
            base_x = (i * 37) % MAP_PX
            base_y = (i * 53) % MAP_PX
            x = (base_x + tick * 2) % MAP_PX
            y = (base_y + tick * speed) % MAP_PX
            pygame.draw.line(
                surf, color,
                (int(x), int(y)),
                (int(x) - 4, int(y) + length), 1
            )

        # Éclairs aléatoires pour stormy
        if weather == "stormy" and random.random() < 0.005:
            flash = pygame.Surface((MAP_PX, MAP_PX), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 80))
            surf.blit(flash, (0, 0))

    elif weather == "windy":
        # Traînées horizontales (effet vent)
        for i in range(40):
            y = (i * 23) % MAP_PX
            length = 30 + (i % 5) * 12
            x = (tick * 4 + i * 67) % (MAP_PX + 100) - 50
            pygame.draw.line(
                surf, (180, 200, 230),
                (int(x), int(y)), (int(x) + length, int(y)), 1
            )


def draw_station(surf, info, jid, tick):
    """Station de recharge avec pulsation électrique."""
    pos = grid_to_screen(info["position"])
    is_busy = info.get("occupied_by") is not None
    color = NEON_RED if is_busy else NEON_GREEN

    # Halo pulsant
    pulse = abs(math.sin(tick * 0.08)) * 4
    blit_glow(surf, color, pos, int(8 + pulse), intensity=5)

    # Plateforme hexagonale stylisée
    radius = 12
    hex_points = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        hex_points.append((
            pos[0] + math.cos(angle) * radius,
            pos[1] + math.sin(angle) * radius
        ))
    pygame.draw.polygon(surf, (15, 20, 30), hex_points)
    pygame.draw.polygon(surf, color, hex_points, 2)

    # Symbole éclair au centre
    bolt_points = [
        (pos[0] + 1, pos[1] - 7),
        (pos[0] - 3, pos[1]),
        (pos[0] + 1, pos[1]),
        (pos[0] - 1, pos[1] + 7),
        (pos[0] + 3, pos[1]),
        (pos[0] - 1, pos[1]),
    ]
    pygame.draw.polygon(surf, (255, 255, 255), bolt_points)


def draw_order_route(surf, order, tick):
    """Route pickup → dropoff avec pointillés animés."""
    pickup = grid_to_screen(order["pickup"])
    dropoff = grid_to_screen(order["dropoff"])

    # Pointillés animés (effet "défilement" le long du segment)
    dx = dropoff[0] - pickup[0]
    dy = dropoff[1] - pickup[1]
    dist = math.hypot(dx, dy)
    if dist == 0:
        return
    n_dots = max(2, int(dist / 10))
    phase = (tick * 0.04) % 1
    for i in range(n_dots):
        t = ((i / n_dots) + phase) % 1
        x = pickup[0] + dx * t
        y = pickup[1] + dy * t
        pygame.draw.circle(surf, (255, 230, 100), (int(x), int(y)), 1)

    # Pickup (losange pulsant jaune)
    pulse_p = 5 + abs(math.sin(tick * 0.12)) * 2.5
    blit_glow(surf, NEON_YELLOW, pickup, int(pulse_p), intensity=4)
    diamond_p = [
        (pickup[0], pickup[1] - 6),
        (pickup[0] + 6, pickup[1]),
        (pickup[0], pickup[1] + 6),
        (pickup[0] - 6, pickup[1]),
    ]
    pygame.draw.polygon(surf, (255, 255, 255), diamond_p, 1)

    # Dropoff (cible cyan)
    pulse_d = 5 + abs(math.cos(tick * 0.12)) * 2.5
    blit_glow(surf, NEON_CYAN, dropoff, int(pulse_d), intensity=4)
    pygame.draw.circle(surf, (255, 255, 255), dropoff, 6, 1)
    pygame.draw.circle(surf, (255, 255, 255), dropoff, 3, 1)


def draw_drone(surf, info, jid, tick, font_mini):
    """Drone avec hélices animées + glow + arc de batterie."""
    pos = grid_to_screen(info["position"])
    status = info.get("status", "idle")
    color = STATUS_COLOR.get(status, NEON_CYAN)
    battery = info.get("battery", 0.0)

    # Ombre au sol (ellipse sombre)
    shadow_surf = pygame.Surface((20, 8), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow_surf, (0, 0, 0, 130), (0, 0, 20, 8))
    surf.blit(shadow_surf, (pos[0] - 10, pos[1] + 6))

    # Trait vers la cible (subtil)
    target = info.get("target")
    if target:
        target_screen = grid_to_screen(target)
        # Ligne pointillée vers la cible
        dx = target_screen[0] - pos[0]
        dy = target_screen[1] - pos[1]
        dist = math.hypot(dx, dy)
        if dist > 0:
            n_pts = int(dist / 8)
            for i in range(n_pts):
                t = i / max(1, n_pts)
                if i % 2 == 0:
                    px = pos[0] + dx * t
                    py = pos[1] + dy * t
                    pygame.draw.circle(surf, color, (int(px), int(py)), 1)

    # Halo principal autour du drone
    blit_glow(surf, color, pos, 7, intensity=5)

    # 4 hélices qui tournent (rotation rapide)
    rotor_radius = 9
    rotation = (tick * 35) % 360
    for i in range(4):
        angle = math.radians(rotation + i * 90)
        ex = pos[0] + math.cos(angle) * rotor_radius
        ey = pos[1] + math.sin(angle) * rotor_radius
        # Trait de l'hélice
        pygame.draw.line(surf, color, pos, (ex, ey), 1)
        # Mini-cercle au bout (rotor)
        pygame.draw.circle(surf, color, (int(ex), int(ey)), 2)

    # Corps central du drone
    pygame.draw.circle(surf, (10, 12, 20), pos, 5)
    pygame.draw.circle(surf, color, pos, 5, 2)

    # ARC DE BATTERIE autour du drone (270° max, démarre à -135°)
    bat_pct = battery / 100.0
    if bat_pct > 0:
        bat_color = (
            NEON_RED if battery < 25 else
            NEON_YELLOW if battery < 60 else
            NEON_GREEN
        )
        bat_rect = pygame.Rect(pos[0] - 16, pos[1] - 16, 32, 32)
        start_angle = math.radians(-135)
        end_angle = math.radians(-135 + 270 * bat_pct)
        # Fond de la jauge (gris)
        try:
            pygame.draw.arc(surf, (40, 45, 60), bat_rect,
                            math.radians(-135), math.radians(135), 2)
        except Exception:
            pass
        # Jauge de batterie remplie
        try:
            pygame.draw.arc(surf, bat_color, bat_rect, start_angle, end_angle, 2)
        except Exception:
            pass

    # Nom du drone en mini-texte
    name = jid.split("@")[0]
    label = font_mini.render(name, True, COLOR_TEXT_DIM)
    surf.blit(label, (pos[0] + 14, pos[1] - 6))


def draw_customer(surf, info, jid, tick):
    """Client : carré pulsant rouge."""
    pos = grid_to_screen(info["position"])
    pulse = abs(math.sin(tick * 0.1)) * 3
    blit_glow(surf, NEON_RED, pos, int(5 + pulse), intensity=3)
    rect = pygame.Rect(pos[0] - 4, pos[1] - 4, 8, 8)
    pygame.draw.rect(surf, NEON_RED, rect, 0, 2)
    pygame.draw.rect(surf, (255, 255, 255), rect, 1, 2)


# =============================================================================
# PANNEAU LATÉRAL MODERNE
# =============================================================================

def draw_panel(surf, fonts, snapshot, tick, status_msg, demo_mode):
    """Panneau latéral droit avec stats, drones, événements."""
    panel_x = MAP_PX
    font_title, font_h, font_med, font_small, font_mini = fonts

    # ===== BACKGROUND avec gradient =====
    for y in range(WINDOW_H):
        t = y / WINDOW_H
        color = lerp_color(COLOR_PANEL_BG_TOP, COLOR_PANEL_BG_BOT, t)
        pygame.draw.line(surf, color, (panel_x, y), (WINDOW_W, y))

    # Trait néon vertical à gauche du panel
    pygame.draw.line(surf, NEON_CYAN, (panel_x, 0), (panel_x, WINDOW_H), 2)

    # ===== TITRE =====
    y = 18
    title_str = "DRONE DELIVERY  ⚡  SMA"
    draw_glow_text(surf, title_str, font_title, NEON_CYAN, (panel_x + 18, y))
    y += 38

    # Sous-titre + mode
    sub = "Système Multi-Agents Cyberpunk Edition"
    surf.blit(font_small.render(sub, True, COLOR_TEXT_DIM), (panel_x + 18, y))
    y += 22

    if demo_mode:
        demo_label = font_small.render(
            "▶ MODE DÉMO (agents non connectés)", True, NEON_MAGENTA
        )
        surf.blit(demo_label, (panel_x + 18, y))
        y += 22

    # Trait de séparation
    pygame.draw.line(surf, COLOR_GRID_BRIGHT,
                     (panel_x + 18, y), (WINDOW_W - 18, y), 1)
    y += 12

    # ===== CARD MÉTÉO =====
    weather = snapshot["weather"]
    weather_color = {
        "clear": NEON_GREEN,
        "windy": NEON_YELLOW,
        "rainy": NEON_BLUE,
        "stormy": NEON_PURPLE,
    }.get(weather, NEON_CYAN)
    weather_icon = {
        "clear": "☀",
        "windy": "🌬",
        "rainy": "🌧",
        "stormy": "⛈",
    }.get(weather, "?")

    card_h = 56
    card_rect = pygame.Rect(panel_x + 16, y, PANEL_W - 32, card_h)
    pygame.draw.rect(surf, (20, 24, 36), card_rect, 0, 6)
    pygame.draw.rect(surf, weather_color, card_rect, 2, 6)
    surf.blit(font_h.render(f"{weather_icon}  Météo", True, COLOR_TEXT_DIM),
              (card_rect.x + 14, card_rect.y + 8))
    draw_glow_text(surf, weather.upper(), font_title, weather_color,
                   (card_rect.x + 14, card_rect.y + 26))
    y += card_h + 14

    # ===== STATS LIVRAISONS (4 mini-cards en grille 2x2) =====
    stats = snapshot["stats"]
    stat_items = [
        ("TOTAL", str(stats["total_orders"]), NEON_CYAN),
        ("EN COURS", str(stats["active_orders"]), NEON_YELLOW),
        ("LIVRÉES", str(stats["deliveries_completed"]), NEON_GREEN),
        ("ÉCHEC", str(stats["deliveries_failed"]), NEON_RED),
    ]
    card_w = (PANEL_W - 48) // 2
    sc_h = 56
    for i, (label, val, col) in enumerate(stat_items):
        col_idx = i % 2
        row_idx = i // 2
        cx = panel_x + 16 + col_idx * (card_w + 16)
        cy = y + row_idx * (sc_h + 10)
        rect = pygame.Rect(cx, cy, card_w, sc_h)
        pygame.draw.rect(surf, (18, 22, 34), rect, 0, 5)
        pygame.draw.rect(surf, col, rect, 1, 5)
        # Label
        surf.blit(font_mini.render(label, True, COLOR_TEXT_DIM),
                  (rect.x + 10, rect.y + 8))
        # Valeur en gros
        draw_glow_text(surf, val, font_title, col,
                       (rect.x + 10, rect.y + 22))
    y += sc_h * 2 + 18

    # ===== LISTE DES DRONES =====
    surf.blit(font_h.render("🚁  FLOTTE DRONES", True, NEON_CYAN),
              (panel_x + 18, y))
    y += 26

    for jid, info in snapshot["drones"].items():
        name = jid.split("@")[0].upper()
        status = info.get("status", "idle")
        bat = info.get("battery", 0)
        st_color = STATUS_COLOR.get(status, NEON_CYAN)
        st_label = STATUS_LABEL.get(status, status.upper())

        # Card du drone
        card_rect = pygame.Rect(panel_x + 16, y, PANEL_W - 32, 36)
        pygame.draw.rect(surf, (18, 22, 34), card_rect, 0, 4)
        pygame.draw.line(surf, st_color,
                         (card_rect.x, card_rect.y),
                         (card_rect.x, card_rect.bottom), 3)

        # LED de statut
        led_pos = (card_rect.x + 16, card_rect.y + 18)
        blit_glow(surf, st_color, led_pos, 4, intensity=3)

        # Nom + statut
        surf.blit(font_med.render(name, True, COLOR_TEXT),
                  (card_rect.x + 28, card_rect.y + 4))
        surf.blit(font_mini.render(st_label, True, st_color),
                  (card_rect.x + 28, card_rect.y + 20))

        # Barre de batterie (côté droit)
        bar_w = 80
        bar_h = 8
        bar_x = card_rect.right - bar_w - 14
        bar_y = card_rect.y + 14
        pygame.draw.rect(surf, (30, 35, 50), (bar_x, bar_y, bar_w, bar_h), 0, 3)
        fill_w = int(bar_w * (bat / 100.0))
        bat_color = (
            NEON_RED if bat < 25 else
            NEON_YELLOW if bat < 60 else
            NEON_GREEN
        )
        if fill_w > 0:
            pygame.draw.rect(surf, bat_color, (bar_x, bar_y, fill_w, bar_h), 0, 3)
        # Valeur batterie en texte
        surf.blit(font_mini.render(f"{bat:5.1f}%", True, COLOR_TEXT_DIM),
                  (bar_x + bar_w - 38, bar_y - 12))
        y += 42

    y += 8
    # Trait de séparation
    pygame.draw.line(surf, COLOR_GRID_BRIGHT,
                     (panel_x + 18, y), (WINDOW_W - 18, y), 1)
    y += 8

    # ===== LOG DES ÉVÉNEMENTS =====
    surf.blit(font_h.render("📡  ÉVÉNEMENTS", True, NEON_CYAN),
              (panel_x + 18, y))
    y += 24

    events = snapshot["events"][-10:]
    for evt in reversed(events):
        if len(evt) > 48:
            evt = evt[:45] + "..."
        surf.blit(font_small.render("›  " + evt, True, COLOR_TEXT_DIM),
                  (panel_x + 18, y))
        y += 17
        if y > WINDOW_H - 30:
            break

    # ===== FOOTER : message d'état =====
    footer = font_mini.render(status_msg, True, COLOR_TEXT_DIM)
    surf.blit(footer, (panel_x + 18, WINDOW_H - 18))


# =============================================================================
# MODE DÉMO (drones fictifs pour montrer le rendu)
# =============================================================================

class DemoSimulation:
    """
    Simule des drones qui se promènent quand les vrais agents ne sont pas connectés.
    BUT : démontrer le visuel du dashboard sans dépendre du système SMA.
    """

    def __init__(self):
        self.active = False
        self.fake_drones = []
        self.fake_stations = [
            ("station1@localhost", (10, 10)),
            ("station2@localhost", (40, 10)),
            ("station3@localhost", (25, 40)),
        ]
        self.fake_customer_counter = 0

    def activate(self):
        if self.active:
            return
        self.active = True
        # Spawn stations
        for jid, pos in self.fake_stations:
            world_state.register_station(jid, pos)

        # Spawn 5 drones avec trajectoires aléatoires
        positions = [(5, 25), (45, 25), (25, 5), (25, 45), (25, 25)]
        for i, pos in enumerate(positions, 1):
            jid = f"drone{i}@localhost"
            world_state.register_drone(jid, pos)
            self.fake_drones.append({
                "jid": jid,
                "pos": [float(pos[0]), float(pos[1])],
                "target": [random.randint(0, GRID_W - 1),
                           random.randint(0, GRID_H - 1)],
                "battery": random.uniform(40, 100),
                "status": random.choice(
                    ["idle", "moving_to_pickup", "carrying"]
                ),
                "phase": random.uniform(0, 6.28),
            })

        # Première commande
        self._spawn_fake_order()
        world_state.log_event("✨ Mode démo activé (agents non connectés)")

    def _spawn_fake_order(self):
        self.fake_customer_counter += 1
        order_id = f"demo_{self.fake_customer_counter}"
        pickup = (random.randint(0, GRID_W - 1), random.randint(0, GRID_H - 1))
        dropoff = (random.randint(0, GRID_W - 1), random.randint(0, GRID_H - 1))
        cust_jid = f"customer{self.fake_customer_counter}@localhost"
        world_state.register_customer(cust_jid, dropoff)
        world_state.add_order(order_id, cust_jid, pickup, dropoff)

    def tick(self, dt):
        if not self.active:
            return

        # Faire bouger les drones
        for d in self.fake_drones:
            # Vers la cible
            tx, ty = d["target"]
            dx = tx - d["pos"][0]
            dy = ty - d["pos"][1]
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                # Arrivé : on change de cible aléatoirement + changement de statut
                d["target"] = [random.randint(0, GRID_W - 1),
                               random.randint(0, GRID_H - 1)]
                d["status"] = random.choice([
                    "idle", "moving_to_pickup", "carrying",
                    "moving_to_station", "charging"
                ])
            else:
                speed = 4.0
                d["pos"][0] += (dx / dist) * speed * dt
                d["pos"][1] += (dy / dist) * speed * dt

            # Batterie qui fluctue
            if d["status"] == "charging":
                d["battery"] = min(100, d["battery"] + 30 * dt)
            else:
                d["battery"] = max(5, d["battery"] - 1.5 * dt)

            # Mise à jour world_state
            world_state.update_drone(
                d["jid"],
                position=(int(d["pos"][0]), int(d["pos"][1])),
                battery=d["battery"],
                status=d["status"],
                target=tuple(d["target"]),
            )

        # Toutes les 3 secondes, nouvelle commande
        if random.random() < dt / 3.0:
            if len([o for o in world_state.snapshot()["orders"].values()
                    if o["status"] not in ("completed", "failed")]) < 5:
                self._spawn_fake_order()

        # Cycle météo aléatoire
        if random.random() < dt / 12.0:
            world_state.set_weather(random.choice(
                ["clear", "clear", "windy", "rainy", "stormy"]
            ))


# =============================================================================
# BOUCLE PRINCIPALE
# =============================================================================

def run_dashboard():
    pygame.init()
    pygame.display.init()
    screen = pygame.display.set_mode(
        (WINDOW_W, WINDOW_H), pygame.DOUBLEBUF
    )
    pygame.display.set_caption("⚡ DRONE DELIVERY SMA — Néon Dashboard")
    clock = pygame.time.Clock()

    # Polices
    def make_font(size, bold=False):
        for name in ["consolas", "courier new", "monospace"]:
            try:
                return pygame.font.SysFont(name, size, bold=bold)
            except Exception:
                pass
        return pygame.font.Font(None, size + 4)

    font_title = make_font(22, bold=True)
    font_h = make_font(15, bold=True)
    font_med = make_font(14)
    font_small = make_font(12)
    font_mini = make_font(10)
    fonts = (font_title, font_h, font_med, font_small, font_mini)

    tick = 0
    last_time = time.time()
    demo = DemoSimulation()
    demo_check_start = time.time()
    running = True

    while running:
        now = time.time()
        dt = now - last_time
        last_time = now
        tick += 1

        # ===== Évents =====
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_d and not demo.active:
                    # Forcer le mode démo avec touche D
                    demo.activate()

        # ===== Mode démo automatique =====
        # Si après 25 secondes aucun drone réel n'est connecté → mode démo
        # (le démarrage des 10 vrais agents SPADE prend ~10-15 secondes)
        if not demo.active and now - demo_check_start > 25:
            snap = world_state.snapshot()
            if len(snap["drones"]) == 0:
                demo.activate()

        # Tick du mode démo (avancer les drones fictifs)
        demo.tick(dt)

        # ===== Lecture état partagé =====
        snapshot = world_state.snapshot()
        drone_count = len(snapshot["drones"])
        if demo.active:
            status_msg = "▶ Mode démo activé — Appuie ÉCHAP pour quitter"
        elif drone_count == 0:
            status_msg = "⏳ En attente des agents... (démo dans quelques secondes)"
        else:
            status_msg = f"🟢 Système connecté — {drone_count} drones actifs"

        # ===== RENDU =====
        screen.fill(COLOR_BG)
        draw_animated_grid(screen, tick)
        draw_weather_particles(screen, snapshot["weather"], tick)

        # Customers (en attente)
        for jid, info in snapshot["customers"].items():
            draw_customer(screen, info, jid, tick)

        # Routes des commandes actives
        for oid, order in snapshot["orders"].items():
            if order["status"] not in ("completed", "failed"):
                draw_order_route(screen, order, tick)

        # Stations
        for jid, info in snapshot["stations"].items():
            draw_station(screen, info, jid, tick)

        # Drones (au-dessus de tout le reste)
        for jid, info in snapshot["drones"].items():
            draw_drone(screen, info, jid, tick, font_mini)

        # Panneau latéral
        draw_panel(screen, fonts, snapshot, tick, status_msg, demo.active)

        pygame.display.flip()
        clock.tick(30)   # 30 FPS

    pygame.quit()
    print("[Dashboard] Fermé proprement")
