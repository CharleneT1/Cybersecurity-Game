#!/usr/bin/env python3
"""
Minimal 2D cyber infection simulation prototype.

This script renders a simplified world map populated with thousands of device
nodes. A single node starts infected and the virus spreads across the network
according to proximity and device similarity rules.

Controls:
    • Close the window to exit.

Requirements:
    • Python 3.9+
    • pygame (``pip install pygame``)
"""
from __future__ import annotations

import math
import random
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame
import pygame.gfxdraw

from map_polygons import LAND_POLYGONS

# Simulation configuration --------------------------------------------------
SEED = 42
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
NODE_COUNT = 10
BACKGROUND_COLOR = (13, 21, 34)
INFECTED_COLOR = (222, 70, 70)
SECURE_COLOR = (70, 200, 120)
VULNERABLE_COLOR = (240, 208, 96)  # unlocked and attackable, not yet infected
LOCKED_COLOR = (56, 66, 80)  # not yet reachable as a target
NODE_RADIUS = 5
MENU_HEIGHT = max(24, int(WINDOW_HEIGHT * 0.03))
UPGRADE_STARTING_POINTS = 10
UPGRADE_NODE_RADIUS = 28

# Attacker-side progression: two nodes start as reachable targets, the rest
# stay locked until a neighboring node is compromised. Attacks are unlocked
# once (like upgrades) then can be launched repeatedly at a small per-attempt
# cost; a successful hit unlocks that node's neighbors and pays out points.
STARTING_TARGET_IDS = (0, 1)
ATTACK_STARTING_POINTS = 10
ATTACK_ATTEMPT_COST = 1
INFECTION_REWARD = 4

# Off-guard odds (attack not favored against the target's device type) scale
# with the target's own vulnerability_score (1-10), so a soft target can still
# fall to the wrong tool while a hardened one mostly won't.
OFF_GUARD_BASE_CHANCE = 0.15
OFF_GUARD_PER_VULN_POINT = 0.05

# Precision-generated (Cartopy + Natural Earth, public domain) equirectangular
# map, exactly 2:1 and spanning the full -180..180 / -90..90 range -- so pixel
# lookups against it agree with the lon/lat math used for node placement. See
# assets/README.md for regeneration instructions.
MAP_IMAGE_PATH = Path("assets/world_map.png")

# Bundled instead of pygame.font.SysFont("arial", ...), which silently
# resolves to whatever the OS happens to have and looks inconsistent
# (or ugly) across machines -- see assets/fonts/LICENSE.txt.
FONT_REGULAR_PATH = Path("assets/fonts/DejaVuSans.ttf")
FONT_BOLD_PATH = Path("assets/fonts/DejaVuSans-Bold.ttf")


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    if path.exists():
        return pygame.font.Font(str(path), size)
    return pygame.font.SysFont("arial", size, bold=bold)


CONNECTION_SECURE_COLOR = (96, 186, 150)
CONNECTION_COMPROMISED_COLOR = (210, 84, 84)

@dataclass(frozen=True)
class ScenarioNodeSpec:
    label: str
    device_type: str
    latitude: float
    longitude: float
    region: str
    location: str
    role: str
    connectivity: Tuple[str, ...]
    vulnerability_score: int  # 1 (hardened) - 10 (soft target); feeds attack odds
    vulnerability_reasoning: str
    lat_jitter: float = 0.35
    lon_jitter: float = 0.45


@dataclass(frozen=True)
class ScenarioConnectionSpec:
    source: int
    target: int
    medium: str
    description: str


SCENARIO_NODE_SPECS: Tuple[ScenarioNodeSpec, ...] = (
    ScenarioNodeSpec(
        label="Madrid Civic Phones",
        device_type="phone",
        latitude=40.4168,
        longitude=-3.7038,
        region="Spain",
        location="Madrid",
        role="Commuters checking transit updates through the municipal network.",
        connectivity=("Municipal Wi-Fi", "LTE", "Bluetooth"),
        vulnerability_score=7,
        vulnerability_reasoning="Personal phones on open municipal Wi-Fi rarely enforce baseline hygiene.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Barcelona Smart Home Hub",
        device_type="iot",
        latitude=41.3874,
        longitude=2.1686,
        region="Spain",
        location="Barcelona",
        role="Controls apartment climate sensors and lighting automations.",
        connectivity=("Fiber Uplink", "Zigbee", "Wi-Fi"),
        vulnerability_score=8,
        vulnerability_reasoning="Consumer IoT hubs ship with default credentials and rarely get firmware updates.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Valencia Remote Offices",
        device_type="computer",
        latitude=39.4699,
        longitude=-0.3763,
        region="Spain",
        location="Valencia",
        role="Analysts tunneling into headquarters through managed VPN desks.",
        connectivity=("Enterprise Wi-Fi", "Ethernet", "VPN Client"),
        vulnerability_score=4,
        vulnerability_reasoning="Managed endpoints with enforced VPN and enterprise patching.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Seville Hospital IoT",
        device_type="iot",
        latitude=37.3891,
        longitude=-5.9845,
        region="Spain",
        location="Seville",
        role="Monitors critical care vitals from connected medical devices.",
        connectivity=("Secured Wi-Fi", "Bluetooth", "Zigbee"),
        vulnerability_score=7,
        vulnerability_reasoning="Medical IoT prioritizes uptime over patching; firmware is often years out of date.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Bilbao Esports PCs",
        device_type="computer",
        latitude=43.2630,
        longitude=-2.9350,
        region="Spain",
        location="Bilbao",
        role="High-end rigs scrimming via low-latency competitive ladders.",
        connectivity=("Fiber LAN", "Wi-Fi 6", "Bluetooth"),
        vulnerability_score=6,
        vulnerability_reasoning="Gaming rigs run frequent third-party mods and overlays with broad permissions.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Lisbon Regional Data Center",
        device_type="server",
        latitude=38.7223,
        longitude=-9.1393,
        region="Portugal",
        location="Lisbon",
        role="Hosts SaaS workloads for Iberian customers with redundancy.",
        connectivity=("Fiber Backbone", "VPN Gateway", "SSH"),
        vulnerability_score=3,
        vulnerability_reasoning="Redundant SaaS infrastructure with hardened SSH access and active monitoring.",
        lat_jitter=0.25,
        lon_jitter=0.35,
    ),
    ScenarioNodeSpec(
        label="Frankfurt VPN Gateway",
        device_type="server",
        latitude=50.1109,
        longitude=8.6821,
        region="Germany",
        location="Frankfurt",
        role="Aggregates secure tunnels for European enterprise tenants.",
        connectivity=("MPLS Backbone", "VPN Concentrator", "SSH"),
        vulnerability_score=3,
        vulnerability_reasoning="Purpose-built VPN concentrator with strict tenant isolation.",
        lat_jitter=0.3,
        lon_jitter=0.3,
    ),
    ScenarioNodeSpec(
        label="Dublin CDN Relay",
        device_type="server",
        latitude=53.3498,
        longitude=-6.2603,
        region="Ireland",
        location="Dublin",
        role="Caches media assets before distributing to Atlantic audiences.",
        connectivity=("Peered Fiber", "HTTPS", "SSH"),
        vulnerability_score=5,
        vulnerability_reasoning="Public-facing cache endpoints trade some hardening for throughput.",
        lat_jitter=0.3,
        lon_jitter=0.3,
    ),
    ScenarioNodeSpec(
        label="New York Trading Desk",
        device_type="computer",
        latitude=40.7128,
        longitude=-74.0060,
        region="United States",
        location="New York City",
        role="Risk models syncing with European exchanges pre-market.",
        connectivity=("Private Fiber", "VPN Client", "SSH"),
        vulnerability_score=5,
        vulnerability_reasoning="High-value target with strict controls, but pre-market time pressure invites shortcuts.",
        lat_jitter=0.3,
        lon_jitter=0.3,
    ),
    ScenarioNodeSpec(
        label="Tokyo Streaming Cluster",
        device_type="server",
        latitude=35.6762,
        longitude=139.6503,
        region="Japan",
        location="Tokyo",
        role="Origin streaming nodes serving Asia-Pacific subscribers.",
        connectivity=("Transpacific Fiber", "HTTPS", "SSH"),
        vulnerability_score=5,
        vulnerability_reasoning="Origin servers are hardened but expose a large HTTPS attack surface.",
        lat_jitter=0.3,
        lon_jitter=0.3,
    ),
)


SCENARIO_CONNECTION_SPECS: Tuple[ScenarioConnectionSpec, ...] = (
    ScenarioConnectionSpec(
        source=0,
        target=1,
        medium="Municipal Wi-Fi Mesh",
        description="Madrid transit handsets join the Barcelona smart-home mesh when riders visit family.",
    ),
    ScenarioConnectionSpec(
        source=0,
        target=2,
        medium="VPN App",
        description="Phones pivot through the Valencia remote work gateway during after-hours check-ins.",
    ),
    ScenarioConnectionSpec(
        source=1,
        target=3,
        medium="Secure Zigbee Bridge",
        description="Hospital sensors receive environment updates from Barcelona apartment automation experts.",
    ),
    ScenarioConnectionSpec(
        source=1,
        target=5,
        medium="HTTPS Telemetry",
        description="Smart home dashboards forward anonymized metrics into Lisbon's SaaS analytics stack.",
    ),
    ScenarioConnectionSpec(
        source=2,
        target=5,
        medium="Enterprise Fiber",
        description="Valencia analysts push daily reports into the Lisbon data center's staging clusters.",
    ),
    ScenarioConnectionSpec(
        source=2,
        target=6,
        medium="Managed VPN",
        description="Remote employees rely on Frankfurt's hardened concentrator for privileged access.",
    ),
    ScenarioConnectionSpec(
        source=3,
        target=4,
        medium="Arena LAN",
        description="Regional esports scrims share match telemetry between Seville and Bilbao arenas.",
    ),
    ScenarioConnectionSpec(
        source=3,
        target=5,
        medium="Clinical Sync",
        description="Seville's hospital charts replicate nightly into Lisbon's redundant data stores.",
    ),
    ScenarioConnectionSpec(
        source=4,
        target=5,
        medium="Low-Latency Fiber",
        description="Bilbao gaming rigs warm their caches from Lisbon to reduce tournament lag.",
    ),
    ScenarioConnectionSpec(
        source=5,
        target=6,
        medium="EU Backbone Peering",
        description="Lisbon and Frankfurt exchange telemetry to balance demand across EU tenants.",
    ),
    ScenarioConnectionSpec(
        source=5,
        target=7,
        medium="Content Distribution",
        description="Lisbon's cache preloads media to Dublin before North American prime-time.",
    ),
    ScenarioConnectionSpec(
        source=6,
        target=8,
        medium="Risk Tunnel",
        description="Frankfurt analytics feed New York trading desks ahead of opening bells.",
    ),
    ScenarioConnectionSpec(
        source=6,
        target=9,
        medium="Threat Intel Share",
        description="Frankfurt relays credential stuffing indicators directly to Tokyo's SOC cluster.",
    ),
    ScenarioConnectionSpec(
        source=7,
        target=8,
        medium="CDN Bridge",
        description="Dublin mirrors highlight videos into Manhattan for overnight streaming bursts.",
    ),
    ScenarioConnectionSpec(
        source=8,
        target=9,
        medium="Peered VPN",
        description="New York and Tokyo coordinate DRM keys for simultaneous content launches.",
    ),
)




@dataclass(slots=True)
class Node:
    """Represents a single device in the network."""

    id: int
    x: float
    y: float
    latitude: float
    longitude: float
    region: str
    location: str
    device_type: str
    connectivity: Tuple[str, ...]
    label: str
    summary: str
    vulnerability_score: int
    vulnerability_reasoning: str
    state: str = "secure"


@dataclass(slots=True)
class Connection:
    source: int
    target: int
    medium: str
    description: str


@dataclass(frozen=True)
class UpgradeNode:
    id: str
    name: str
    description: str
    cost: int
    position: Tuple[int, int]
    prerequisites: Tuple[str, ...] = ()
    effective_against: Tuple[str, ...] = ()  # attack-tree only; unused by defense upgrades


@dataclass
class MenuButton:
    label: str
    key: str
    rect: pygame.Rect


UPGRADE_TREE: Tuple[UpgradeNode, ...] = (
    UpgradeNode(
        id="awareness",
        name="Awareness Campaigns",
        description="Launch engaging security awareness pushes to shrink phishing risk.",
        cost=1,
        position=(80, 70),
    ),
    UpgradeNode(
        id="patch_automation",
        name="Patch Automation",
        description="Automate change windows so fixes deploy quickly across fleets.",
        cost=1,
        position=(220, 70),
    ),
    UpgradeNode(
        id="segmentation",
        name="Network Segmentation",
        description="Carve defensive tiers to contain intrusions and limit lateral spread.",
        cost=2,
        position=(150, 160),
        prerequisites=("awareness", "patch_automation"),
    ),
    UpgradeNode(
        id="threat_hunting",
        name="Threat Hunting AI",
        description="Deploy adaptive analytics that surface stealthy adversary behavior.",
        cost=2,
        position=(70, 250),
        prerequisites=("segmentation",),
    ),
    UpgradeNode(
        id="deception",
        name="Deception Nets",
        description="Spin up believable decoys that waste attacker time and signal breaches.",
        cost=2,
        position=(230, 250),
        prerequisites=("segmentation",),
    ),
    UpgradeNode(
        id="resilience",
        name="Resilience Drills",
        description="Rehearse coordinated response so recovery is fast when incidents occur.",
        cost=3,
        position=(150, 340),
        prerequisites=("threat_hunting", "deception"),
    ),
)


ATTACK_TREE: Tuple[UpgradeNode, ...] = (
    UpgradeNode(
        id="credential_guess",
        name="Credential Guessing",
        description="Try leaked or common passwords against exposed logins.",
        cost=2,
        position=(80, 70),
        effective_against=("phone", "computer"),
    ),
    UpgradeNode(
        id="phishing_link",
        name="Phishing Link",
        description="Trick a user into opening a crafted payload link.",
        cost=2,
        position=(220, 70),
        effective_against=("computer", "iot"),
    ),
    UpgradeNode(
        id="exploit_kit",
        name="Exploit Kit",
        description="Chain a known CVE against an unpatched service.",
        cost=3,
        position=(150, 170),
        prerequisites=("credential_guess", "phishing_link"),
        effective_against=("server", "iot"),
    ),
    UpgradeNode(
        id="zero_day_broker",
        name="Zero-Day Broker",
        description="Buy a fresh, unpatched exploit effective against anything.",
        cost=4,
        position=(150, 270),
        prerequisites=("exploit_kit",),
        effective_against=("phone", "computer", "iot", "server"),
    ),
)


def build_menu_buttons() -> List[MenuButton]:
    buttons: List[MenuButton] = []
    labels = (
        ("Attacks", "attacks"),
        ("Upgrades", "upgrades"),
        ("Virus Progress", "virus"),
        ("Settings", "settings"),
    )
    button_width = WINDOW_WIDTH // len(labels)
    x = 0
    for index, (label, key) in enumerate(labels):
        width = button_width if index < len(labels) - 1 else WINDOW_WIDTH - x
        rect = pygame.Rect(x, 0, width, MENU_HEIGHT)
        buttons.append(MenuButton(label=label, key=key, rect=rect))
        x += width
    return buttons
def _point_in_polygon(lon: float, lat: float, polygon: Sequence[Tuple[float, float]]) -> bool:
    inside = False
    x, y = lon, lat
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if (y1 > y) == (y2 > y):
            continue
        denominator = y2 - y1
        if denominator == 0:
            continue
        slope = (x2 - x1) / denominator
        intersection_x = slope * (y - y1) + x1
        if x < intersection_x:
            inside = not inside
    return inside


def is_on_land(lon: float, lat: float) -> bool:
    for polygon in LAND_POLYGONS:
        if _point_in_polygon(lon, lat, polygon):
            return True
    return False
@dataclass(frozen=True)
class Projection:
    map_width: float
    map_height: float
    scale: float
    offset_x: float
    offset_y: float

    def to_screen(self, lon: float, lat: float) -> Tuple[float, float]:
        x = (lon + 180.0) / 360.0 * self.map_width * self.scale + self.offset_x
        y = (1.0 - (lat + 90.0) / 180.0) * self.map_height * self.scale + self.offset_y
        return x, y


def generate_nodes(
    rng: random.Random, projection: Projection, is_land: Callable[[float, float], bool]
) -> List[Node]:
    if len(SCENARIO_NODE_SPECS) != NODE_COUNT:
        raise ValueError(
            "Scenario configuration mismatch: expected "
            f"{NODE_COUNT} nodes but described {len(SCENARIO_NODE_SPECS)}"
        )

    nodes: List[Node] = []
    for idx, spec in enumerate(SCENARIO_NODE_SPECS):
        lat = spec.latitude
        lon = spec.longitude
        for _ in range(40):
            jittered_lat = rng.uniform(
                spec.latitude - spec.lat_jitter, spec.latitude + spec.lat_jitter
            )
            jittered_lon = rng.uniform(
                spec.longitude - spec.lon_jitter, spec.longitude + spec.lon_jitter
            )
            if is_land(jittered_lon, jittered_lat):
                lat, lon = jittered_lat, jittered_lon
                break
        else:
            if not is_land(lon, lat):
                print(f"Could not verify land for {spec.label}, forcing placement.")

                # raise RuntimeError(
                    # f"Unable to place node '{spec.label}' on land using the provided map."
                # )

        x, y = projection.to_screen(lon, lat)
        summary = (
            f"Type: {spec.device_type.title()}\n"
            f"Location: {spec.location}, {spec.region}\n"
            f"Connectivity: {', '.join(spec.connectivity)}\n"
            f"Role: {spec.role}"
        )

        nodes.append(
            Node(
                id=idx,
                x=x,
                y=y,
                latitude=lat,
                longitude=lon,
                region=spec.region,
                location=spec.location,
                device_type=spec.device_type,
                connectivity=spec.connectivity,
                label=spec.label,
                summary=summary,
                vulnerability_score=spec.vulnerability_score,
                vulnerability_reasoning=spec.vulnerability_reasoning,
            )
        )

    return nodes


def build_connections() -> List[Connection]:
    connections: List[Connection] = []
    for spec in SCENARIO_CONNECTION_SPECS:
        connections.append(
            Connection(
                source=spec.source,
                target=spec.target,
                medium=spec.medium,
                description=spec.description,
            )
        )
    return connections


def build_neighbor_lists_from_connections(
    node_count: int, connections: Sequence[Connection]
) -> List[List[int]]:
    neighbor_lists: List[List[int]] = [[] for _ in range(node_count)]
    for connection in connections:
        neighbor_lists[connection.source].append(connection.target)
        neighbor_lists[connection.target].append(connection.source)
    for idx in range(node_count):
        neighbor_lists[idx] = sorted(set(neighbor_lists[idx]))
    return neighbor_lists


def off_guard_success_chance(node: Node) -> float:
    return min(0.9, OFF_GUARD_BASE_CHANCE + node.vulnerability_score * OFF_GUARD_PER_VULN_POINT)


def attempt_attack(rng: random.Random, node: Node, attack: UpgradeNode) -> bool:
    """Resolve a launched attack against its target. Favored device types always
    succeed; anything else rolls against the target's own vulnerability score,
    matching the original design note that vector suitability *and* per-device
    weakness should both affect success odds."""

    if node.device_type in attack.effective_against:
        return True
    return rng.random() < off_guard_success_chance(node)


def unlock_neighbors(
    node_id: int, nodes: List[Node], neighbors: Sequence[Sequence[int]]
) -> None:
    for neighbor_idx in neighbors[node_id]:
        if nodes[neighbor_idx].state == "locked":
            nodes[neighbor_idx].state = "vulnerable"


LABEL_SPECS: Sequence[Tuple[str, float, float, Tuple[int, int]]] = (
    ("North America", 54.0, -110.0, (-80, -30)),
    ("South America", -20.0, -60.0, (-70, 0)),
    ("Europe", 54.0, 15.0, (-40, -40)),
    ("Africa", 10.0, 20.0, (-30, 0)),
    ("Middle East", 27.0, 45.0, (-50, -10)),
    ("Russia", 63.0, 90.0, (-40, -50)),
    ("South Asia", 22.0, 78.0, (-60, 0)),
    ("East Asia", 33.0, 113.0, (-60, -10)),
    ("SE Asia", 10.0, 104.0, (-40, 10)),
    ("Oceania", -18.0, 135.0, (-60, 10)),
)


def draw_labels(surface: pygame.Surface, font: pygame.font.Font, projection: Projection) -> None:
    label_color = (200, 220, 240)
    for text, lat, lon, (dx, dy) in LABEL_SPECS:
        x, y = projection.to_screen(lon, lat)
        label_surface = font.render(text, True, label_color)
        rect = label_surface.get_rect()
        rect.center = (int(x) + dx, int(y) + dy)
        surface.blit(label_surface, rect)


_glow_cache: Dict[Tuple[Tuple[int, int, int], int, int], pygame.Surface] = {}


def _glow_surface(color: Tuple[int, int, int], base_radius: int, extra: int) -> pygame.Surface:
    key = (color, base_radius, extra)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached
    span = (base_radius + extra) * 2
    surface = pygame.Surface((span, span), pygame.SRCALPHA)
    center = span // 2
    layers = 5
    for i in range(layers, 0, -1):
        t = i / layers
        radius = int(base_radius + extra * t)
        alpha = int(85 * (1 - t) ** 2)
        pygame.gfxdraw.filled_circle(surface, center, center, radius, (*color, alpha))
    _glow_cache[key] = surface
    return surface


def draw_nodes(surface: pygame.Surface, nodes: Sequence[Node]) -> None:
    pulse = (math.sin(pygame.time.get_ticks() / 320.0) + 1) / 2  # 0..1, gentle breathing rhythm

    for node in nodes:
        if node.state == "infected":
            color = INFECTED_COLOR
        elif node.state == "vulnerable":
            color = VULNERABLE_COLOR
        elif node.state == "locked":
            color = LOCKED_COLOR
        else:
            color = SECURE_COLOR

        cx, cy = int(node.x), int(node.y)

        if node.state == "infected":
            extra = 8 + int(6 * pulse)
            glow = _glow_surface(color, NODE_RADIUS, extra)
            surface.blit(glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2), special_flags=pygame.BLEND_RGBA_ADD)
        elif node.state == "vulnerable":
            glow = _glow_surface(color, NODE_RADIUS, 7)
            surface.blit(glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2), special_flags=pygame.BLEND_RGBA_ADD)

        radius = NODE_RADIUS - 1 if node.state == "locked" else NODE_RADIUS
        pygame.gfxdraw.filled_circle(surface, cx, cy, radius, color)
        pygame.gfxdraw.aacircle(surface, cx, cy, radius, color)


def draw_connections(
    surface: pygame.Surface,
    nodes: Sequence[Node],
    connections: Sequence[Connection],
    hovered: Optional[Connection] = None,
) -> None:
    for connection in connections:
        source = nodes[connection.source]
        target = nodes[connection.target]
        compromised = source.state == "infected" or target.state == "infected"
        color = CONNECTION_COMPROMISED_COLOR if compromised else CONNECTION_SECURE_COLOR
        width = 4 if hovered is connection else 2
        pygame.draw.line(
            surface,
            color,
            (int(source.x), int(source.y)),
            (int(target.x), int(target.y)),
            width,
        )


def wrap_text_lines(text: str, width: int = 34) -> List[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=width)


def _point_to_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    abx = bx - ax
    aby = by - ay
    if abx == 0 and aby == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)
    t = max(0.0, min(1.0, t))
    closest_x = ax + t * abx
    closest_y = ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def find_connection_under_point(
    connections: Sequence[Connection],
    nodes: Sequence[Node],
    pos: Tuple[int, int],
    threshold: float = 6.0,
) -> Optional[Connection]:
    px, py = pos
    for connection in connections:
        source = nodes[connection.source]
        target = nodes[connection.target]
        distance = _point_to_segment_distance(px, py, source.x, source.y, target.x, target.y)
        if distance <= threshold:
            return connection
    return None


def format_connection_description(
    connection: Connection, nodes: Sequence[Node]
) -> List[str]:
    source = nodes[connection.source]
    target = nodes[connection.target]
    compromised = source.state == "infected" or target.state == "infected"
    status = "Compromised" if compromised else "Secure"
    lines = [f"{source.label} ↔ {target.label}", ""]
    lines.append(f"Medium: {connection.medium}")
    lines.extend(wrap_text_lines(f"Detail: {connection.description}", width=38))
    lines.append(f"Status: {status}")
    return lines


def draw_tooltip(
    surface: pygame.Surface,
    font: pygame.font.Font,
    lines: Sequence[str],
    position: Tuple[int, int],
) -> None:
    if not lines:
        return

    padding_x, padding_y = 10, 6
    rendered = [font.render(line, True, (230, 238, 255)) for line in lines]
    max_line_width = max((surface_line.get_width() for surface_line in rendered), default=0)
    width = max(120, max_line_width + padding_x * 2)
    height = sum(surface_line.get_height() for surface_line in rendered) + padding_y * 2

    x, y = position
    if x + width > WINDOW_WIDTH - 10:
        x = WINDOW_WIDTH - width - 10
    if y + height > WINDOW_HEIGHT - 10:
        y = WINDOW_HEIGHT - height - 10

    rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, (20, 32, 48), rect, border_radius=8)
    pygame.draw.rect(surface, (80, 110, 150), rect, 2, border_radius=8)

    cursor_y = rect.y + padding_y
    for line_surface in rendered:
        surface.blit(line_surface, (rect.x + padding_x, cursor_y))
        cursor_y += line_surface.get_height()


def format_node_description(node: Node) -> List[str]:
    lines = [node.label, ""]
    lines.extend(node.summary.splitlines())
    lines.append(f"Status: {node.state.title()}")
    lines.append(f"Vulnerability: {node.vulnerability_score}/10")
    return lines


def find_node_under_point(nodes: Sequence[Node], pos: Tuple[int, int]) -> Optional[Node]:
    px, py = pos
    for node in nodes:
        if math.hypot(node.x - px, node.y - py) <= NODE_RADIUS + 6:
            return node
    return None


def draw_menu(surface: pygame.Surface, buttons: Sequence[MenuButton], active: Optional[str], font: pygame.font.Font) -> None:
    accent = (110, 170, 230)
    for button in buttons:
        is_active = button.key == active
        base_color = (32, 46, 66)
        active_color = (52, 78, 112)
        color = active_color if is_active else base_color
        pygame.draw.rect(surface, color, button.rect)
        pygame.draw.rect(surface, (58, 78, 102), button.rect, 1)
        label_color = (235, 242, 255) if is_active else (172, 188, 210)
        label_surface = font.render(button.label, True, label_color)
        label_rect = label_surface.get_rect(center=button.rect.center)
        surface.blit(label_surface, label_rect)
        if is_active:
            underline = pygame.Rect(button.rect.x, button.rect.bottom - 3, button.rect.width, 3)
            pygame.draw.rect(surface, accent, underline)


def draw_stat_chip(
    surface: pygame.Surface, font: pygame.font.Font, x: int, y: int,
    label: str, value: str, color: Tuple[int, int, int],
) -> int:
    """Draws a single rounded stat pill and returns its width, so callers can
    lay out several chips left-to-right without pre-measuring text twice."""

    text_surface = font.render(f"{label}  {value}", True, (222, 230, 245))
    height = 28
    width = text_surface.get_width() + 40
    rect = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, (21, 29, 44), rect, border_radius=height // 2)
    pygame.draw.rect(surface, color, rect, 1, border_radius=height // 2)
    dot_center = (rect.x + 16, rect.centery)
    pygame.gfxdraw.filled_circle(surface, dot_center[0], dot_center[1], 4, color)
    pygame.gfxdraw.aacircle(surface, dot_center[0], dot_center[1], 4, color)
    surface.blit(text_surface, (rect.x + 26, rect.centery - text_surface.get_height() // 2))
    return width


def draw_hud_chips(
    surface: pygame.Surface, font: pygame.font.Font, x: int, y: int,
    vulnerable_count: int, infected_count: int, locked_count: int,
    integrity_percent: float, attack_points: int,
) -> None:
    gap = 8
    stats = (
        ("Targets", str(vulnerable_count), VULNERABLE_COLOR),
        ("Infected", str(infected_count), INFECTED_COLOR),
        ("Locked", str(locked_count), LOCKED_COLOR),
        ("Integrity", f"{integrity_percent:0.0f}%", SECURE_COLOR),
        ("Attack Pts", str(attack_points), (120, 165, 225)),
    )
    cursor_x = x
    for label, value, color in stats:
        cursor_x += draw_stat_chip(surface, font, cursor_x, y, label, value, color) + gap


TREE_TOP_PADDING = 34  # keeps the first row of nodes clear of the title/points text


def compute_upgrade_centers(
    panel_rect: pygame.Rect, tree: Sequence[UpgradeNode] = UPGRADE_TREE
) -> Dict[str, Tuple[int, int]]:
    centers: Dict[str, Tuple[int, int]] = {}
    for node in tree:
        centers[node.id] = (
            panel_rect.x + node.position[0],
            panel_rect.y + node.position[1] + TREE_TOP_PADDING,
        )
    return centers


def draw_panel_shadow(surface: pygame.Surface, rect: pygame.Rect, offset: int = 6) -> None:
    shadow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=14)
    surface.blit(shadow, (rect.x + offset // 2, rect.y + offset))


def draw_upgrade_panel(
    surface: pygame.Surface,
    panel_rect: pygame.Rect,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    upgrade_state: Dict[str, bool],
    upgrade_points: int,
    mouse_pos: Tuple[int, int],
    tree: Sequence[UpgradeNode] = UPGRADE_TREE,
    title: str = "Defense Upgrade Tree",
    points_label: str = "Upgrade Points",
) -> Optional[UpgradeNode]:
    draw_panel_shadow(surface, panel_rect)
    pygame.draw.rect(surface, (18, 28, 45), panel_rect, border_radius=12)
    pygame.draw.rect(surface, (84, 116, 168), panel_rect, 2, border_radius=12)

    title_surface = font.render(title, True, (230, 238, 255))
    surface.blit(title_surface, (panel_rect.x + 16, panel_rect.y + 12))

    points_surface = small_font.render(
        f"{points_label}: {upgrade_points}", True, (196, 212, 240)
    )
    surface.blit(points_surface, (panel_rect.x + 16, panel_rect.y + 46))

    centers = compute_upgrade_centers(panel_rect, tree)

    # Draw connections first so nodes overlay the lines.
    for node in tree:
        node_center = centers[node.id]
        for prereq in node.prerequisites:
            prereq_center = centers.get(prereq)
            if prereq_center:
                pygame.draw.line(surface, (60, 82, 120), prereq_center, node_center, 4)

    hovered: Optional[UpgradeNode] = None
    mouse_x, mouse_y = mouse_pos
    for node in tree:
        center_x, center_y = centers[node.id]
        purchased = upgrade_state.get(node.id, False)
        prerequisites_met = all(upgrade_state.get(req, False) for req in node.prerequisites)
        affordable = upgrade_points >= node.cost
        available = prerequisites_met and not purchased and affordable

        if purchased:
            fill_color = (88, 168, 112)
        elif available:
            fill_color = (86, 126, 208)
        elif prerequisites_met and not affordable:
            fill_color = (110, 96, 150)
        else:
            fill_color = (54, 62, 82)

        pygame.draw.circle(surface, fill_color, (center_x, center_y), UPGRADE_NODE_RADIUS)
        pygame.draw.circle(surface, (18, 28, 45), (center_x, center_y), UPGRADE_NODE_RADIUS, 3)

        name_lines = wrap_text_lines(node.name, width=14)
        line_height = small_font.get_linesize()
        total_height = line_height * len(name_lines)
        for index, line in enumerate(name_lines):
            line_surface = small_font.render(line, True, (240, 244, 255))
            text_y = int(center_y - total_height / 2 + index * line_height)
            line_rect = line_surface.get_rect(center=(center_x, text_y))
            surface.blit(line_surface, line_rect)

        cost_surface = small_font.render(f"{node.cost} pt", True, (200, 210, 240))
        cost_rect = cost_surface.get_rect(
            center=(center_x, int(center_y + UPGRADE_NODE_RADIUS - 10))
        )
        surface.blit(cost_surface, cost_rect)

        if math.hypot(mouse_x - center_x, mouse_y - center_y) <= UPGRADE_NODE_RADIUS:
            hovered = node

    return hovered


def get_upgrade_under_point(
    panel_rect: pygame.Rect,
    mouse_pos: Tuple[int, int],
    tree: Sequence[UpgradeNode] = UPGRADE_TREE,
) -> Optional[UpgradeNode]:
    centers = compute_upgrade_centers(panel_rect, tree)
    mx, my = mouse_pos
    for node in tree:
        center = centers[node.id]
        if math.hypot(mx - center[0], my - center[1]) <= UPGRADE_NODE_RADIUS:
            return node
    return None


def can_purchase_upgrade(node: UpgradeNode, state: Dict[str, bool], points: int) -> bool:
    if state.get(node.id):
        return False
    if points < node.cost:
        return False
    return all(state.get(req, False) for req in node.prerequisites)


def draw_text_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    title: str,
    lines: Sequence[str],
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
) -> None:
    draw_panel_shadow(surface, rect)
    pygame.draw.rect(surface, (18, 28, 45), rect, border_radius=12)
    pygame.draw.rect(surface, (84, 116, 168), rect, 2, border_radius=12)

    title_surface = title_font.render(title, True, (230, 238, 255))
    surface.blit(title_surface, (rect.x + 16, rect.y + 12))

    y = rect.y + 52
    for line in lines:
        for chunk in wrap_text_lines(line, width=40):
            text_surface = body_font.render(chunk, True, (210, 222, 245))
            surface.blit(text_surface, (rect.x + 16, y))
            y += text_surface.get_height() + 2
        y += 6


ATTACK_ROW_HEIGHT = 60
TARGET_REASONING_WRAP_WIDTH = 42


def target_panel_layout(
    node: Node, last_result: str, small_font: pygame.font.Font
) -> Dict[str, int]:
    """Y-offsets (relative to panel_rect.y) for the target panel's dynamic
    content. The reasoning text's wrapped line count varies per node, so this
    is computed once and shared between drawing and click hit-testing --
    they can never disagree about where the attack rows actually are."""

    line_height = small_font.get_linesize()
    reasoning_lines = wrap_text_lines(node.vulnerability_reasoning, width=TARGET_REASONING_WRAP_WIDTH)
    reasoning_top = 86
    points_top = reasoning_top + len(reasoning_lines) * (line_height + 1) + 10
    rows_top = points_top + 26 + (24 if last_result else 0)
    return {"reasoning_top": reasoning_top, "points_top": points_top, "rows_top": rows_top}


def compute_target_rows(
    panel_rect: pygame.Rect,
    unlocked_attacks: Sequence[UpgradeNode],
    rows_top: int,
) -> List[Tuple[UpgradeNode, pygame.Rect]]:
    rows: List[Tuple[UpgradeNode, pygame.Rect]] = []
    for index, attack in enumerate(unlocked_attacks):
        row_rect = pygame.Rect(
            panel_rect.x + 12,
            panel_rect.y + rows_top + index * (ATTACK_ROW_HEIGHT + 8),
            panel_rect.width - 24,
            ATTACK_ROW_HEIGHT,
        )
        rows.append((attack, row_rect))
    return rows


def draw_target_panel(
    surface: pygame.Surface,
    panel_rect: pygame.Rect,
    title_font: pygame.font.Font,
    body_font: pygame.font.Font,
    small_font: pygame.font.Font,
    node: Node,
    attack_state: Dict[str, bool],
    attack_points: int,
    last_result: str,
    mouse_pos: Tuple[int, int],
) -> List[Tuple[UpgradeNode, pygame.Rect]]:
    draw_panel_shadow(surface, panel_rect)
    pygame.draw.rect(surface, (18, 28, 45), panel_rect, border_radius=12)
    pygame.draw.rect(surface, (168, 96, 96), panel_rect, 2, border_radius=12)

    title_surface = title_font.render(f"Target: {node.label}", True, (255, 236, 236))
    surface.blit(title_surface, (panel_rect.x + 16, panel_rect.y + 12))

    info_surface = small_font.render(
        f"{node.device_type.title()} - {node.location}, {node.region}", True, (210, 190, 190)
    )
    surface.blit(info_surface, (panel_rect.x + 16, panel_rect.y + 44))

    vuln_color = (230, 150, 150) if node.vulnerability_score >= 7 else (
        (230, 200, 140) if node.vulnerability_score >= 5 else (170, 210, 180)
    )
    vuln_surface = small_font.render(
        f"Vulnerability: {node.vulnerability_score}/10", True, vuln_color
    )
    surface.blit(vuln_surface, (panel_rect.x + 16, panel_rect.y + 66))

    layout = target_panel_layout(node, last_result, small_font)

    reasoning_y = panel_rect.y + layout["reasoning_top"]
    for line in wrap_text_lines(node.vulnerability_reasoning, width=TARGET_REASONING_WRAP_WIDTH):
        reasoning_surface = small_font.render(line, True, (170, 180, 195))
        surface.blit(reasoning_surface, (panel_rect.x + 16, reasoning_y))
        reasoning_y += reasoning_surface.get_height() + 1

    points_surface = small_font.render(
        f"Attack Points: {attack_points}", True, (230, 200, 200)
    )
    surface.blit(points_surface, (panel_rect.x + 16, panel_rect.y + layout["points_top"]))

    if last_result:
        result_surface = small_font.render(last_result, True, (240, 210, 140))
        surface.blit(result_surface, (panel_rect.x + 16, panel_rect.y + layout["rows_top"] - 24))

    unlocked_attacks = [attack for attack in ATTACK_TREE if attack_state.get(attack.id, False)]
    rows = compute_target_rows(panel_rect, unlocked_attacks, layout["rows_top"])

    if not unlocked_attacks:
        hint_surface = small_font.render(
            "No attacks unlocked yet -- open Attacks to buy one.", True, (200, 180, 180)
        )
        surface.blit(hint_surface, (panel_rect.x + 16, panel_rect.y + layout["rows_top"]))
        return []

    mouse_x, mouse_y = mouse_pos
    for attack, row_rect in rows:
        hovered = row_rect.collidepoint(mouse_x, mouse_y)
        affordable = attack_points >= ATTACK_ATTEMPT_COST
        favored = node.device_type in attack.effective_against

        pygame.draw.rect(surface, (62, 80, 108) if hovered else (46, 60, 82), row_rect, border_radius=8)
        pygame.draw.rect(surface, (90, 120, 168), row_rect, 1, border_radius=8)

        name_surface = body_font.render(attack.name, True, (235, 240, 250))
        surface.blit(name_surface, (row_rect.x + 10, row_rect.y + 6))

        odds_text = (
            "Favored target"
            if favored
            else f"~{int(off_guard_success_chance(node) * 100)}% odds"
        )
        odds_surface = small_font.render(
            f"{odds_text} · launch: {ATTACK_ATTEMPT_COST} pt",
            True,
            (170, 220, 190) if favored else (210, 190, 150),
        )
        surface.blit(odds_surface, (row_rect.x + 10, row_rect.y + 30))

        if not affordable:
            locked_surface = small_font.render("Not enough points", True, (150, 100, 100))
            locked_rect = locked_surface.get_rect()
            locked_rect.topright = (row_rect.right - 10, row_rect.y + 10)
            surface.blit(locked_surface, locked_rect)

    return rows


def get_target_row_under_point(
    panel_rect: pygame.Rect,
    attack_state: Dict[str, bool],
    node: Node,
    last_result: str,
    small_font: pygame.font.Font,
    mouse_pos: Tuple[int, int],
) -> Optional[UpgradeNode]:
    unlocked_attacks = [attack for attack in ATTACK_TREE if attack_state.get(attack.id, False)]
    layout = target_panel_layout(node, last_result, small_font)
    rows = compute_target_rows(panel_rect, unlocked_attacks, layout["rows_top"])
    for attack, row_rect in rows:
        if row_rect.collidepoint(mouse_pos):
            return attack
    return None


# Tutorial gate: this social-engineering/OSINT puzzle is the sole starting
# point. The rest of the map (Madrid, Barcelona, and everything they unlock)
# only becomes reachable after logging into Sara's laptop.
SaraPost = Tuple[str, str, bool]  # (author, text, has_dog_photo)

SARA_POSTS: Tuple[SaraPost, ...] = (
    (
        "Sara Müller",
        "New job announcement! So excited to join Nordwind Logistics as a Security "
        "Analyst. Reach me at sara.muller@nordwind-logistics.com",
        False,
    ),
    (
        "Sara Müller",
        "Buddy turned 3 today and insisted on a whole cake to himself.",
        True,
    ),
    (
        "Sara Müller",
        "Home office day with my favorite coworker supervising every video call.",
        False,
    ),
)
SARA_CORRECT_USERNAME = "sara.muller@nordwind-logistics.com"
SARA_CORRECT_PASSWORD = "Buddy3"
SARA_HINTS: Tuple[str, ...] = (
    "Look for a way she'd be reached professionally -- that's the username.",
    "One post pairs a name with a number. People reuse exactly that as a password.",
    f'Try "{SARA_CORRECT_PASSWORD}" for the password.',
)


def draw_dog_icon(surface: pygame.Surface, center: Tuple[int, int], radius: int) -> None:
    cx, cy = center
    ear_color = (150, 108, 66)
    head_color = (196, 152, 102)
    pygame.draw.polygon(
        surface, ear_color,
        [(cx - radius, cy - radius * 0.2), (cx - radius * 1.4, cy - radius * 1.3), (cx - radius * 0.3, cy - radius * 0.6)],
    )
    pygame.draw.polygon(
        surface, ear_color,
        [(cx + radius, cy - radius * 0.2), (cx + radius * 1.4, cy - radius * 1.3), (cx + radius * 0.3, cy - radius * 0.6)],
    )
    pygame.draw.circle(surface, head_color, (cx, cy), radius)
    eye_offset = radius * 0.35
    pygame.draw.circle(surface, (40, 30, 24), (int(cx - eye_offset), int(cy - eye_offset * 0.3)), max(2, radius // 8))
    pygame.draw.circle(surface, (40, 30, 24), (int(cx + eye_offset), int(cy - eye_offset * 0.3)), max(2, radius // 8))
    pygame.draw.ellipse(
        surface, (120, 84, 56),
        (cx - radius * 0.3, cy + radius * 0.15, radius * 0.6, radius * 0.45),
    )


@dataclass
class TextField:
    rect: pygame.Rect
    label: str
    value: str = ""
    masked: bool = False
    active: bool = False

    def display_text(self) -> str:
        return "•" * len(self.value) if self.masked else self.value


def draw_text_field(surface: pygame.Surface, font: pygame.font.Font, field: TextField) -> None:
    border_color = (120, 160, 210) if field.active else (70, 90, 115)
    pygame.draw.rect(surface, (16, 24, 38), field.rect, border_radius=6)
    pygame.draw.rect(surface, border_color, field.rect, 2, border_radius=6)
    text_surface = font.render(field.display_text(), True, (225, 235, 250))
    surface.blit(text_surface, (field.rect.x + 10, field.rect.y + (field.rect.height - text_surface.get_height()) // 2))
    if field.active and (pygame.time.get_ticks() // 500) % 2 == 0:
        cursor_x = field.rect.x + 10 + text_surface.get_width() + 2
        pygame.draw.line(
            surface, (225, 235, 250),
            (cursor_x, field.rect.y + 6), (cursor_x, field.rect.bottom - 6), 2,
        )


def run_intro_scene(screen: pygame.Surface, clock: pygame.time.Clock) -> bool:
    """Sara's laptop OSINT/credential-guessing tutorial. Returns False if the
    player quit the window during the intro (main() should exit immediately
    without starting the map game), True once the login succeeds."""

    title_font = load_font(24, bold=True)
    header_font = load_font(18, bold=True)
    body_font = load_font(16)
    small_font = load_font(14)
    field_font = load_font(16)

    feed_rect = pygame.Rect(40, 90, 700, 560)
    login_rect = pygame.Rect(780, 90, 460, 340)

    username_field = TextField(pygame.Rect(login_rect.x + 24, login_rect.y + 84, login_rect.width - 48, 36), "Username")
    password_field = TextField(pygame.Rect(login_rect.x + 24, login_rect.y + 160, login_rect.width - 48, 36), "Password", masked=True)
    username_field.active = True

    login_button = pygame.Rect(login_rect.x + 24, login_rect.y + 220, login_rect.width - 48, 40)

    message = ""
    message_color = (200, 200, 210)
    attempts = 0

    running = True
    solved = False
    while running and not solved:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if username_field.rect.collidepoint(event.pos):
                    username_field.active = True
                    password_field.active = False
                elif password_field.rect.collidepoint(event.pos):
                    password_field.active = True
                    username_field.active = False
                elif login_button.collidepoint(event.pos):
                    attempts += 1
                    username_ok = username_field.value.strip().lower() == SARA_CORRECT_USERNAME.lower()
                    password_ok = password_field.value == SARA_CORRECT_PASSWORD
                    if username_ok and password_ok:
                        message = "Access granted. Loading the wider network..."
                        message_color = (140, 220, 160)
                        solved = True
                    elif username_ok:
                        message = "Username looks right. Password's wrong -- check her posts for a name + number."
                        message_color = (230, 190, 130)
                    else:
                        message = "That username doesn't look right -- how would you actually reach Sara?"
                        message_color = (220, 140, 140)
                else:
                    username_field.active = False
                    password_field.active = False
            elif event.type == pygame.KEYDOWN:
                active_field = username_field if username_field.active else (
                    password_field if password_field.active else None
                )
                if event.key == pygame.K_TAB:
                    username_field.active, password_field.active = password_field.active, username_field.active
                elif event.key == pygame.K_RETURN:
                    if username_field.active:
                        username_field.active, password_field.active = False, True
                    else:
                        pygame.event.post(pygame.event.Event(
                            pygame.MOUSEBUTTONDOWN, pos=login_button.center, button=1
                        ))
                elif active_field is not None:
                    if event.key == pygame.K_BACKSPACE:
                        active_field.value = active_field.value[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        active_field.value += event.unicode

        screen.fill((10, 14, 22))

        title_surface = title_font.render("Recon: Sara's Laptop", True, (235, 240, 250))
        screen.blit(title_surface, (40, 36))
        subtitle_surface = small_font.render(
            "OSINT her public posts, then try logging into her work account.", True, (150, 165, 190)
        )
        screen.blit(subtitle_surface, (40, 66))

        pygame.draw.rect(screen, (16, 22, 34), feed_rect, border_radius=12)
        pygame.draw.rect(screen, (60, 78, 105), feed_rect, 2, border_radius=12)
        feed_title = header_font.render("Sara Müller -- public profile", True, (225, 232, 245))
        screen.blit(feed_title, (feed_rect.x + 20, feed_rect.y + 16))

        post_y = feed_rect.y + 56
        for author, text, has_dog in SARA_POSTS:
            post_rect = pygame.Rect(feed_rect.x + 20, post_y, feed_rect.width - 40, 130 if has_dog else 90)
            pygame.draw.rect(screen, (22, 30, 46), post_rect, border_radius=10)
            pygame.draw.rect(screen, (48, 62, 86), post_rect, 1, border_radius=10)
            author_surface = body_font.render(author, True, (210, 220, 240))
            screen.blit(author_surface, (post_rect.x + 14, post_rect.y + 10))
            if has_dog:
                draw_dog_icon(screen, (post_rect.x + 50, post_rect.y + 70), 28)
                text_x = post_rect.x + 100
            else:
                text_x = post_rect.x + 14
            for line_idx, line in enumerate(wrap_text_lines(text, width=48 if not has_dog else 32)):
                line_surface = small_font.render(line, True, (185, 195, 215))
                screen.blit(line_surface, (text_x, post_rect.y + 36 + line_idx * 18))
            post_y += post_rect.height + 16

        pygame.draw.rect(screen, (16, 22, 34), login_rect, border_radius=12)
        pygame.draw.rect(screen, (60, 78, 105), login_rect, 2, border_radius=12)
        login_title = header_font.render("Nordwind Logistics -- Account Access", True, (225, 232, 245))
        screen.blit(login_title, (login_rect.x + 24, login_rect.y + 16))

        username_label = small_font.render("Username", True, (160, 175, 200))
        screen.blit(username_label, (username_field.rect.x, username_field.rect.y - 20))
        draw_text_field(screen, field_font, username_field)

        password_label = small_font.render("Password", True, (160, 175, 200))
        screen.blit(password_label, (password_field.rect.x, password_field.rect.y - 20))
        draw_text_field(screen, field_font, password_field)

        pygame.draw.rect(screen, (70, 110, 160), login_button, border_radius=8)
        login_label = body_font.render("Log In", True, (240, 245, 255))
        login_label_rect = login_label.get_rect(center=login_button.center)
        screen.blit(login_label, login_label_rect)

        if message:
            for idx, line in enumerate(wrap_text_lines(message, width=46)):
                message_surface = small_font.render(line, True, message_color)
                screen.blit(message_surface, (login_rect.x + 24, login_button.bottom + 16 + idx * 18))

        if attempts >= 2 and not solved:
            hint_index = min(attempts - 2, len(SARA_HINTS) - 1)
            hint_surface = small_font.render(f"Hint: {SARA_HINTS[hint_index]}", True, (150, 180, 210))
            screen.blit(hint_surface, (login_rect.x + 24, login_rect.bottom - 28))

        pygame.display.flip()

    if solved:
        # Brief pause so "Access granted" is actually readable before the map appears.
        pygame.display.flip()
        pygame.time.wait(1200)
    return solved


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Cyber Defense Prototype")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    if not run_intro_scene(screen, clock):
        pygame.quit()
        return

    if not MAP_IMAGE_PATH.exists():
        raise FileNotFoundError(
            f"World map image not found at {MAP_IMAGE_PATH.resolve()}. "
            "See assets/README.md to regenerate it."
        )

    background_image = pygame.image.load(str(MAP_IMAGE_PATH)).convert_alpha()
    map_width, map_height = background_image.get_size()
    usable_height = WINDOW_HEIGHT - MENU_HEIGHT - 40
    scale = min(WINDOW_WIDTH / map_width, usable_height / map_height)
    scaled_size = (int(map_width * scale), int(map_height * scale))
    background_surface = pygame.transform.smoothscale(background_image, scaled_size)
    offset_x = (WINDOW_WIDTH - scaled_size[0]) / 2
    offset_y = MENU_HEIGHT + (WINDOW_HEIGHT - MENU_HEIGHT - scaled_size[1]) / 2
    background_rect = background_surface.get_rect()
    background_rect.topleft = (round(offset_x), round(offset_y))

    rng = random.Random(SEED)

    projection = Projection(
        map_width=map_width,
        map_height=map_height,
        scale=scale,
        offset_x=background_rect.x,
        offset_y=background_rect.y,
    )

    # Node placement still uses the traced-polygon land test (is_on_land), not
    # a pixel-color sample of the background image -- that keeps placement
    # exact regardless of the image's art style, and it's already validated
    # against every curated node in this scenario.
    nodes = generate_nodes(rng, projection, is_on_land)
    connections = build_connections()
    neighbors = build_neighbor_lists_from_connections(len(nodes), connections)

    # Two nodes start as reachable targets; everything else stays locked until
    # a neighboring node is successfully compromised (see unlock_neighbors()).
    for node in nodes:
        node.state = "vulnerable" if node.id in STARTING_TARGET_IDS else "locked"

    label_font = load_font(18)
    hud_font = load_font(15, bold=True)
    tooltip_font = load_font(16)
    menu_font = load_font(max(18, int(MENU_HEIGHT * 0.6)), bold=True)
    panel_title_font = load_font(20, bold=True)
    panel_body_font = load_font(16)

    menu_buttons = build_menu_buttons()
    upgrade_state: Dict[str, bool] = {node.id: False for node in UPGRADE_TREE}
    upgrade_points = UPGRADE_STARTING_POINTS
    attack_state: Dict[str, bool] = {attack.id: False for attack in ATTACK_TREE}
    attack_points = ATTACK_STARTING_POINTS
    selected_target: Optional[int] = None
    last_attack_result = ""
    active_panel: Optional[str] = None

    panel_margin = 24
    panel_width = 340
    panel_rect = pygame.Rect(
        WINDOW_WIDTH - panel_width - panel_margin,
        MENU_HEIGHT + panel_margin,
        panel_width,
        WINDOW_HEIGHT - MENU_HEIGHT - panel_margin * 2,
    )

    running = True

    while running:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = event.pos
                clicked_button = False
                for button in menu_buttons:
                    if button.rect.collidepoint(mouse_pos):
                        active_panel = None if active_panel == button.key else button.key
                        clicked_button = True
                        break

                if clicked_button:
                    continue

                if active_panel == "upgrades" and panel_rect.collidepoint(mouse_pos):
                    selected_upgrade = get_upgrade_under_point(panel_rect, mouse_pos, UPGRADE_TREE)
                    if selected_upgrade and can_purchase_upgrade(
                        selected_upgrade, upgrade_state, upgrade_points
                    ):
                        upgrade_state[selected_upgrade.id] = True
                        upgrade_points -= selected_upgrade.cost
                    continue

                if active_panel == "attacks" and panel_rect.collidepoint(mouse_pos):
                    selected_attack = get_upgrade_under_point(panel_rect, mouse_pos, ATTACK_TREE)
                    if selected_attack and can_purchase_upgrade(
                        selected_attack, attack_state, attack_points
                    ):
                        attack_state[selected_attack.id] = True
                        attack_points -= selected_attack.cost
                    continue

                if (
                    active_panel == "target"
                    and selected_target is not None
                    and panel_rect.collidepoint(mouse_pos)
                ):
                    target_node = nodes[selected_target]
                    chosen_attack = get_target_row_under_point(
                        panel_rect, attack_state, target_node, last_attack_result,
                        tooltip_font, mouse_pos,
                    )
                    if chosen_attack and attack_points >= ATTACK_ATTEMPT_COST:
                        attack_points -= ATTACK_ATTEMPT_COST
                        if attempt_attack(rng, target_node, chosen_attack):
                            target_node.state = "infected"
                            unlock_neighbors(target_node.id, nodes, neighbors)
                            attack_points += INFECTION_REWARD
                            last_attack_result = ""
                            active_panel = None
                            selected_target = None
                        else:
                            last_attack_result = (
                                f"{chosen_attack.name} failed -- try again or pick another vector."
                            )
                    continue

                clicked_node = find_node_under_point(nodes, mouse_pos)
                if clicked_node and clicked_node.state == "vulnerable":
                    selected_target = clicked_node.id
                    active_panel = "target"
                    last_attack_result = ""

        screen.fill(BACKGROUND_COLOR)
        screen.blit(background_surface, background_rect)
        draw_labels(screen, label_font, projection)

        mouse_pos = pygame.mouse.get_pos()
        hovered_connection = find_connection_under_point(connections, nodes, mouse_pos)
        draw_connections(screen, nodes, connections, hovered_connection)
        draw_nodes(screen, nodes)

        hovered_node = find_node_under_point(nodes, mouse_pos)

        if hovered_node:
            pygame.draw.circle(
                screen,
                (250, 250, 255),
                (int(hovered_node.x), int(hovered_node.y)),
                NODE_RADIUS + 4,
                2,
            )

        infected_count = sum(1 for node in nodes if node.state == "infected")
        vulnerable_count = sum(1 for node in nodes if node.state == "vulnerable")
        locked_count = sum(1 for node in nodes if node.state == "locked")
        integrity_percent = 100.0 * (1 - infected_count / len(nodes))
        draw_hud_chips(
            screen, hud_font, 20, MENU_HEIGHT + 12,
            vulnerable_count, infected_count, locked_count, integrity_percent, attack_points,
        )

        pygame.draw.rect(screen, (18, 26, 38), (0, 0, WINDOW_WIDTH, MENU_HEIGHT))
        draw_menu(screen, menu_buttons, active_panel, menu_font)

        panel_blocks_hover = (
            active_panel in ("upgrades", "attacks", "target")
            and panel_rect.collidepoint(mouse_pos)
        )

        hovered_tree_node: Optional[UpgradeNode] = None
        active_tree_state: Optional[Dict[str, bool]] = None
        if active_panel == "upgrades":
            hovered_tree_node = draw_upgrade_panel(
                screen,
                panel_rect,
                panel_title_font,
                panel_body_font,
                upgrade_state,
                upgrade_points,
                mouse_pos,
                tree=UPGRADE_TREE,
                title="Defense Upgrade Tree",
                points_label="Upgrade Points",
            )
            active_tree_state = upgrade_state
        elif active_panel == "attacks":
            hovered_tree_node = draw_upgrade_panel(
                screen,
                panel_rect,
                panel_title_font,
                panel_body_font,
                attack_state,
                attack_points,
                mouse_pos,
                tree=ATTACK_TREE,
                title="Attack Tree",
                points_label="Attack Points",
            )
            active_tree_state = attack_state
        elif active_panel == "target" and selected_target is not None:
            draw_target_panel(
                screen,
                panel_rect,
                panel_title_font,
                panel_body_font,
                tooltip_font,
                nodes[selected_target],
                attack_state,
                attack_points,
                last_attack_result,
                mouse_pos,
            )
        elif active_panel == "virus":
            draw_text_panel(
                screen,
                panel_rect,
                "Virus Progress",
                [
                    f"Compromised: {infected_count} of {len(nodes)} devices",
                    f"Reachable targets right now: {vulnerable_count}  ·  Still locked: {locked_count}",
                    f"Network integrity holding at {integrity_percent:0.1f}%.",
                    "Click a highlighted (amber) node on the map to pick an attack and try",
                    "to compromise it. A successful hit unlocks that device's neighbors.",
                ],
                panel_title_font,
                panel_body_font,
            )
        elif active_panel == "settings":
            draw_text_panel(
                screen,
                panel_rect,
                "Settings",
                [
                    "Audio, pacing, and colorblind accessibility controls will live here.",
                    "For now you can adjust simulation speed and device density directly",
                    "in the configuration constants at the top of main.py.",
                ],
                panel_title_font,
                panel_body_font,
            )

        if hovered_node and not panel_blocks_hover:
            draw_tooltip(
                screen,
                tooltip_font,
                format_node_description(hovered_node),
                (mouse_pos[0] + 16, mouse_pos[1] + 16),
            )

        elif hovered_connection and not panel_blocks_hover:
            draw_tooltip(
                screen,
                tooltip_font,
                format_connection_description(hovered_connection, nodes),
                (mouse_pos[0] + 16, mouse_pos[1] + 16),
            )

        if hovered_tree_node and active_tree_state is not None and panel_blocks_hover:
            tooltip_lines = [hovered_tree_node.name, ""]
            tooltip_lines.extend(
                wrap_text_lines(hovered_tree_node.description, width=38)
            )
            tooltip_lines.append(f"Cost: {hovered_tree_node.cost} point(s)")
            unlocked = active_tree_state.get(hovered_tree_node.id, False)
            prerequisites = (
                ", ".join(hovered_tree_node.prerequisites)
                if hovered_tree_node.prerequisites
                else "None"
            )
            tooltip_lines.append(f"Unlocked: {'Yes' if unlocked else 'No'}")
            tooltip_lines.append(f"Requires: {prerequisites}")
            if hovered_tree_node.effective_against:
                tooltip_lines.append(
                    f"Effective vs: {', '.join(hovered_tree_node.effective_against)}"
                )
            draw_tooltip(
                screen,
                tooltip_font,
                tooltip_lines,
                (mouse_pos[0] + 16, mouse_pos[1] + 16),
            )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
