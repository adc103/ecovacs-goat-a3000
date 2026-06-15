"""SVG map renderer for GOAT A3000 LiDAR mower.

Renders all zone/path/obstacle/dock data received via onMI/onArI MQTT
messages into an SVG suitable for display in Home Assistant's image entity.

Data structure from onMI/onArI payloads:
  Each entry: [group_id, field1, field2, ...]
  field[1] on entry[0]: dock outline (prefix 's1')
  field[1] on entry[1]: connector paths (compound prefix e.g. '3,1,4')
  Other fields with simple int prefix <= 20: zone polygons
  Fields with compound prefix and coords: connector path polygons
  Fields with int prefix >= 100: LiDAR-detected obstacle outlines

Zone types:
  Zone 1 = no-go zone (orange/red hatched, matches app style)
  Zones 2-5 = mowing zones (bright green fills)
  Connector paths = passage corridors between zones (light grey)
  Obstacles = trees, rocks, garden features (brown outlines)
"""

from __future__ import annotations

import logging
import math
from typing import Any

_LOGGER = logging.getLogger(__name__)

# App-matching colors
_ZONE_GREEN       = "#5ab552"   # bright lawn green (matches app)
_ZONE_GREEN_DARK  = "#3d7a36"   # stroke
_PATH_FILL        = "#c8c8c8"   # light grey path (matches app)
_PATH_STROKE      = "#a0a0a0"
_NO_GO_FILL       = "#e8743a"   # orange (matches app no-go color)
_NO_GO_STROKE     = "#cc5520"
_OBSTACLE_STROKE  = "#8B6914"   # subtle brown
_DOCK_COLOR       = "#ffe605"
_MOWER_COLOR      = "#00aaff"
_BACKGROUND       = "#c8d8c0"   # light grey-green background (like app)

# Different green tones for multiple zones
_ZONE_COLORS = [
    (_ZONE_GREEN,  _ZONE_GREEN_DARK),
    ("#52a555",    "#366e38"),
    ("#4aaa7a",    "#2d7a55"),
    ("#52aa90",    "#357a62"),
    ("#5aaa70",    "#3a7a4a"),
]

# Zone IDs that are no-go zones
_NO_GO_ZONE_IDS = {1}


def _parse_coords(coord_str: str) -> list[tuple[int, int]]:
    """Parse semicolon-separated x,y coordinate string."""
    points = []
    for part in coord_str.split(";"):
        part = part.strip()
        if "," not in part:
            continue
        try:
            x, y = part.split(",", 1)
            points.append((int(x), int(y)))
        except (ValueError, TypeError):
            continue
    return points


def _path_to_centerline(pts: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], float]:
    """Extract centerline and average width from a corridor polygon.

    The polygon traces one side of the corridor then the other.
    We split at the midpoint of the perimeter and pair opposite points.
    Returns (centerline_points, avg_width_mm).
    """
    if len(pts) < 6:
        return pts, 2000.0

    # Cumulative arc length along the polygon perimeter
    cum: list[float] = [0.0]
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        cum.append(cum[-1] + math.sqrt(dx * dx + dy * dy))

    # Split at perimeter midpoint
    mid = cum[-1] / 2
    split = min(range(len(cum)), key=lambda i: abs(cum[i] - mid))

    side_a = pts[:split + 1]
    side_b = list(reversed(pts[split:]))
    n = min(len(side_a), len(side_b))
    if n < 2:
        return pts[: len(pts) // 2], 2000.0

    centerline: list[tuple[int, int]] = []
    widths: list[float] = []
    for i in range(n):
        ax, ay = side_a[i]
        bx, by = side_b[i]
        centerline.append(((ax + bx) // 2, (ay + by) // 2))
        widths.append(math.sqrt((ax - bx) ** 2 + (ay - by) ** 2))

    avg_width = sum(widths) / len(widths) if widths else 2000.0
    return centerline, avg_width


def parse_onmi_entry(entry: list) -> dict:
    """Parse a single onMI/onArI entry into structured data."""
    result: dict = {
        "zone_polygons": {},
        "path_polygons": [],
        "obstacle_polygons": [],
        "dock_outline": [],
    }

    if not isinstance(entry, list):
        return result

    for j, field in enumerate(entry):
        if j == 0:
            continue
        if not isinstance(field, str) or "," not in field:
            continue

        parts = field.split(";")
        prefix = parts[0]
        coords = [p for p in parts[1:] if "," in p]
        if len(coords) < 3:
            continue

        pts = _parse_coords(";".join(coords))
        if len(pts) < 3:
            continue

        if prefix == "s1":
            if not result["dock_outline"]:
                result["dock_outline"] = pts

        elif "," in prefix:
            result["path_polygons"].append((prefix, pts))

        else:
            try:
                zone_id = int(prefix.split(",")[0])
            except (ValueError, TypeError):
                continue

            if zone_id >= 100:
                result["obstacle_polygons"].append((zone_id, pts))
            elif 1 <= zone_id <= 20:
                existing = result["zone_polygons"].get(zone_id)
                if existing is None or len(pts) > len(existing):
                    result["zone_polygons"][zone_id] = pts

    return result


def render_mower_map_from_store(
    zone_store: dict[int, str],
    positions: list[Any] | None = None,
    trace_points: list[str] | None = None,
    path_store: list[tuple[str, str]] | None = None,
    obstacle_store: list[tuple[int, str]] | None = None,
    dock_outline_store: list[tuple[int, int]] | None = None,
    no_go_ids: set[int] | None = None,
    mower_heading: int = 0,
) -> str | None:
    """Render full mower map SVG from all available data stores."""
    if not zone_store and not path_store:
        return None

    if no_go_ids is None:
        no_go_ids = _NO_GO_ZONE_IDS

    # Parse all polygon data
    zone_polygons: dict[int, list[tuple[int, int]]] = {}
    for zone_id, coords_str in zone_store.items():
        pts = _parse_coords(coords_str)
        if len(pts) >= 3:
            zone_polygons[zone_id] = pts

    path_polygons: list[tuple[str, list[tuple[int, int]]]] = []
    if path_store:
        seen: set = set()
        for label, coords_str in path_store:
            pts = _parse_coords(coords_str)
            key = (label, len(pts))
            if len(pts) >= 3 and key not in seen:
                seen.add(key)
                path_polygons.append((label, pts))

    obstacle_polygons: list[tuple[int, list[tuple[int, int]]]] = []
    if obstacle_store:
        for obs_id, coords_str in obstacle_store:
            pts = _parse_coords(coords_str)
            if len(pts) >= 3:
                obstacle_polygons.append((obs_id, pts))

    dock_outline = dock_outline_store or []

    if not zone_polygons and not path_polygons:
        return None

    # Compute bounds
    all_x: list[int] = [0]
    all_y: list[int] = [0]
    for pts in zone_polygons.values():
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)
    for _, pts in path_polygons:
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    span = max(max_x - min_x, max_y - min_y)
    pad = max(span * 0.04, 1000)

    svg_w = max_x - min_x + pad * 2
    svg_h = max_y - min_y + pad * 2
    sw = max(svg_w, svg_h) * 0.0012
    font = max(svg_w, svg_h) * 0.019
    dock_r = max(svg_w, svg_h) * 0.014

    def to_svg(x: int, y: int) -> tuple[float, float]:
        return (x - min_x + pad, max_y - y + pad)

    def pts_to_poly(pts: list[tuple[int, int]]) -> str:
        return " ".join(
            f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in pts)
        )

    def pts_to_path(pts: list[tuple[int, int]]) -> str:
        """Convert points to SVG path with rounded joins for smooth corridors."""
        if not pts:
            return ""
        svg_pts = [to_svg(x, y) for x, y in pts]
        d = f"M {svg_pts[0][0]:.0f},{svg_pts[0][1]:.0f}"
        for sx, sy in svg_pts[1:]:
            d += f" L {sx:.0f},{sy:.0f}"
        return d

    elements: list[str] = []

    # 1. Connector paths — rendered as layered strokes to look like a road/passage
    # Road effect: dark border -> light fill -> white dashed centerline
    path_stroke_w = max(svg_w, svg_h) * 0.022  # narrower than before

    for _, pts in path_polygons:
        if len(pts) < 2:
            continue
        svg_pts = [to_svg(x, y) for x, y in pts]
        d = f"M {svg_pts[0][0]:.0f},{svg_pts[0][1]:.0f}"
        for sx, sy in svg_pts[1:]:
            d += f" L {sx:.0f},{sy:.0f}"

        # Layer 1: dark border (widest)
        elements.append(
            f'<path d="{d}" fill="none" '
            f'stroke="#888888" stroke-width="{path_stroke_w:.0f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        # Layer 2: light grey road surface
        elements.append(
            f'<path d="{d}" fill="none" '
            f'stroke="#d8d8d8" stroke-width="{path_stroke_w * 0.72:.0f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        # Layer 3: white dashed centerline
        dash = path_stroke_w * 0.8
        gap = path_stroke_w * 0.6
        elements.append(
            f'<path d="{d}" fill="none" '
            f'stroke="white" stroke-opacity="0.7" '
            f'stroke-width="{path_stroke_w * 0.12:.0f}" '
            f'stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-dasharray="{dash:.0f} {gap:.0f}"/>'
        )

    # 2. Mowing zones
    color_idx = 0
    for zid, pts in sorted(zone_polygons.items()):
        if zid in no_go_ids:
            continue
        fill, stroke = _ZONE_COLORS[color_idx % len(_ZONE_COLORS)]
        color_idx += 1
        p = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{p}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw:.0f}" '
            f'stroke-linejoin="round"/>'
        )
        svg_pts = [to_svg(x, y) for x, y in pts]
        cx = sum(q[0] for q in svg_pts) / len(svg_pts)
        cy = sum(q[1] for q in svg_pts) / len(svg_pts)
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="{font:.0f}" '
            f'fill="white" font-weight="bold" font-family="sans-serif" '
            f'filter="url(#shadow)">Zone {zid}</text>'
        )

    # 3. No-go zones — orange hatched like app
    hatch_size = sw * 8
    for zid in sorted(no_go_ids):
        if zid not in zone_polygons:
            continue
        p = pts_to_poly(zone_polygons[zid])
        elements.append(
            f'<polygon points="{p}" fill="url(#nogo-hatch)" '
            f'stroke="{_NO_GO_STROKE}" stroke-width="{sw:.0f}" '
            f'stroke-linejoin="round"/>'
        )
        svg_pts = [to_svg(x, y) for x, y in zone_polygons[zid]]
        cx = sum(q[0] for q in svg_pts) / len(svg_pts)
        cy = sum(q[1] for q in svg_pts) / len(svg_pts)
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="{font:.0f}" '
            f'fill="white" font-weight="bold" font-family="sans-serif">⛔</text>'
        )

    # 4. Obstacles — subtle brown outlines only
    for obs_id, pts in obstacle_polygons:
        p = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{p}" fill="{_OBSTACLE_STROKE}" fill-opacity="0.25" '
            f'stroke="{_OBSTACLE_STROKE}" stroke-width="{sw:.0f}" '
            f'stroke-opacity="0.6" stroke-linejoin="round"/>'
        )

    # 5. Mowing path traces
    if trace_points:
        for trace in trace_points:
            trace_pts = _parse_coords(trace)
            if len(trace_pts) < 2:
                continue
            d = pts_to_path(trace_pts)
            elements.append(
                f'<path d="{d}" fill="none" '
                f'stroke="white" stroke-opacity="0.5" '
                f'stroke-width="{sw*0.6:.0f}" stroke-linecap="round"/>'
            )

    # 6. Dock outline (subtle yellow shape)
    if dock_outline and len(dock_outline) >= 3:
        p = pts_to_poly(dock_outline)
        elements.append(
            f'<polygon points="{p}" fill="{_DOCK_COLOR}" fill-opacity="0.3" '
            f'stroke="{_DOCK_COLOR}" stroke-width="{sw:.0f}"/>'
        )

    # 7. Dock marker
    dx, dy = to_svg(0, 0)
    elements.append(
        f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="{dock_r:.0f}" '
        f'fill="{_DOCK_COLOR}" stroke="white" stroke-width="{sw*1.5:.0f}"/>'
    )
    elements.append(
        f'<text x="{dx:.0f}" y="{dy:.0f}" text-anchor="middle" '
        f'dominant-baseline="middle" font-size="{dock_r * 1.1:.0f}" '
        f'fill="#333" font-weight="bold" font-family="sans-serif">⌂</text>'
    )

    # 8. Mower position
    if positions:
        for pos in positions:
            try:
                px = getattr(pos, "x", None)
                py = getattr(pos, "y", None)
                pos_type = str(getattr(pos, "type", "")).lower()
                if px is not None and py is not None and "deebot" in pos_type:
                    if int(px) != 0 or int(py) != 0:
                        sx, sy = to_svg(int(px), int(py))
                        elements.append(
                            f'<circle cx="{sx:.0f}" cy="{sy:.0f}" '
                            f'r="{dock_r * 0.8:.0f}" fill="{_MOWER_COLOR}" '
                            f'stroke="white" stroke-width="{sw*1.5:.0f}"/>'
                        )
            except Exception:
                pass

    # Build defs (hatch pattern + text shadow)
    hatch_w = sw * 10
    defs = (
        f'<defs>'
        f'<pattern id="nogo-hatch" patternUnits="userSpaceOnUse" '
        f'width="{hatch_w:.0f}" height="{hatch_w:.0f}" patternTransform="rotate(45)">'
        f'<rect width="{hatch_w:.0f}" height="{hatch_w:.0f}" fill="{_NO_GO_FILL}" fill-opacity="0.7"/>'
        f'<line x1="0" y1="0" x2="0" y2="{hatch_w:.0f}" '
        f'stroke="{_NO_GO_STROKE}" stroke-width="{sw*2:.0f}" stroke-opacity="0.5"/>'
        f'</pattern>'
        f'<filter id="shadow" x="-5%" y="-5%" width="110%" height="110%">'
        f'<feDropShadow dx="0" dy="0" stdDeviation="{sw*2:.0f}" flood-color="black" flood-opacity="0.6"/>'
        f'</filter>'
        f'</defs>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">'
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="{_BACKGROUND}"/>'
        + defs
        + "".join(elements)
        + "</svg>"
    )


# Legacy stub
def render_mower_map(map_subsets: list[Any], positions: list[Any] | None = None) -> str | None:
    return None
