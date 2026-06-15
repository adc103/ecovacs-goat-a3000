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

Zone types (from getAreaSet):
  Zone 1 = no-go zone (red hatched)
  Zones 2,3,4,5 = mowing zones (colored fills)
  Connector paths = passage corridors between zones
  Obstacles = trees, rocks, garden features detected by LiDAR
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Mowing zone fill colors (fill, stroke)
_ZONE_COLORS = [
    ("#1a6b3a", "#2dcc5a"),  # green
    ("#1a4a7a", "#4a9eff"),  # blue
    ("#4a2a7a", "#8a5eff"),  # purple
    ("#1a6a5a", "#2dccaa"),  # teal
    ("#6b5a1a", "#ccaa2d"),  # gold
]

_NO_GO_FILL = "#7a0000"
_NO_GO_STROKE = "#ff4444"
_PATH_FILL = "#2a3a2a"
_PATH_STROKE = "#5a7a5a"
_OBSTACLE_FILL = "#8B4513"
_OBSTACLE_STROKE = "#cd853f"
_DOCK_COLOR = "#ffe605"
_MOWER_COLOR = "#00aaff"
_BACKGROUND = "#0d1f0d"

# Zone IDs that are no-go zones (from getAreaSet type=nc/no-go pattern)
_NO_GO_ZONE_IDS = {1}
# Zone IDs that are mowing zones
_MOWING_ZONE_IDS = {2, 3, 4, 5, 6, 7, 8, 9}


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


def parse_onmi_entry(entry: list) -> dict:
    """Parse a single onMI/onArI entry into structured data.

    Returns dict with keys:
      zone_polygons: {zone_id: [(x,y), ...]}
      path_polygons: [(label, [(x,y), ...])]
      obstacle_polygons: [(obs_id, [(x,y), ...])]
      dock_outline: [(x,y), ...]
    """
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
            continue  # group/zone ID header
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
            # Dock station outline
            if not result["dock_outline"]:
                result["dock_outline"] = pts

        elif "," in prefix:
            # Compound prefix = connector path between zones
            result["path_polygons"].append((prefix, pts))

        else:
            try:
                zone_id = int(prefix.split(",")[0])
            except (ValueError, TypeError):
                continue

            if zone_id >= 100:
                # LiDAR-detected obstacle
                result["obstacle_polygons"].append((zone_id, pts))
            elif 1 <= zone_id <= 20:
                # Zone polygon — keep best (most detailed)
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
) -> str | None:
    """Render full mower map SVG from all available data stores.

    Args:
        zone_store: {zone_id: coordinates_str} for zone polygons
        positions: List of Position objects (mower location)
        trace_points: Mowing path trace coordinate strings
        path_store: [(label, coordinates_str)] for connector paths
        obstacle_store: [(obs_id, coordinates_str)] for LiDAR obstacles
        dock_outline_store: [(x,y)] for dock station shape
        no_go_ids: Set of zone IDs that are no-go zones
    """
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
        seen = set()
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
    sw = max(svg_w, svg_h) * 0.0015
    font = max(svg_w, svg_h) * 0.02
    dock_r = max(svg_w, svg_h) * 0.013

    def to_svg(x: int, y: int) -> tuple[float, float]:
        return (x - min_x + pad, max_y - y + pad)

    def pts_to_poly(pts: list[tuple[int, int]]) -> str:
        return " ".join(
            f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in pts)
        )

    elements: list[str] = []
    color_idx = 0

    # 1. Connector paths (rendered first, behind zones)
    for _, pts in path_polygons:
        p = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{p}" fill="{_PATH_FILL}" fill-opacity="0.95" '
            f'stroke="{_PATH_STROKE}" stroke-width="{sw:.0f}"/>'
        )

    # 2. Mowing zones
    for zid, pts in sorted(zone_polygons.items()):
        if zid in no_go_ids:
            continue
        fill, stroke = _ZONE_COLORS[color_idx % len(_ZONE_COLORS)]
        color_idx += 1
        p = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{p}" fill="{fill}" fill-opacity="0.75" '
            f'stroke="{stroke}" stroke-width="{sw:.0f}"/>'
        )
        svg_pts = [to_svg(x, y) for x, y in pts]
        cx = sum(q[0] for q in svg_pts) / len(svg_pts)
        cy = sum(q[1] for q in svg_pts) / len(svg_pts)
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="{font:.0f}" fill="white" '
            f'font-weight="bold" font-family="sans-serif">Zone {zid}</text>'
        )

    # 3. No-go zones
    for zid in sorted(no_go_ids):
        if zid not in zone_polygons:
            continue
        p = pts_to_poly(zone_polygons[zid])
        elements.append(
            f'<polygon points="{p}" fill="{_NO_GO_FILL}" fill-opacity="0.7" '
            f'stroke="{_NO_GO_STROKE}" stroke-width="{sw:.0f}" '
            f'stroke-dasharray="{sw*4:.0f}"/>'
        )
        svg_pts = [to_svg(x, y) for x, y in zone_polygons[zid]]
        cx = sum(q[0] for q in svg_pts) / len(svg_pts)
        cy = sum(q[1] for q in svg_pts) / len(svg_pts)
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" '
            f'dominant-baseline="middle" font-size="{font:.0f}" fill="white" '
            f'font-weight="bold" font-family="sans-serif">⛔</text>'
        )

    # 4. Obstacles
    for obs_id, pts in obstacle_polygons:
        p = pts_to_poly(pts)
        if len(pts) >= 20:
            elements.append(
                f'<polygon points="{p}" fill="{_OBSTACLE_FILL}" fill-opacity="0.6" '
                f'stroke="{_OBSTACLE_STROKE}" stroke-width="{sw*1.5:.0f}"/>'
            )
        else:
            elements.append(
                f'<polygon points="{p}" fill="none" '
                f'stroke="{_OBSTACLE_STROKE}" stroke-width="{sw*1.5:.0f}" '
                f'stroke-opacity="0.7"/>'
            )

    # 5. Mowing path traces
    if trace_points:
        for trace in trace_points:
            pts = _parse_coords(trace)
            if len(pts) < 2:
                continue
            pts_str = " ".join(
                f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in pts)
            )
            elements.append(
                f'<polyline points="{pts_str}" fill="none" '
                f'stroke="rgba(255,255,255,0.5)" stroke-width="{sw*0.6:.0f}"/>'
            )

    # 6. Dock outline
    if dock_outline and len(dock_outline) >= 3:
        p = pts_to_poly(dock_outline)
        elements.append(
            f'<polygon points="{p}" fill="{_DOCK_COLOR}" fill-opacity="0.25" '
            f'stroke="{_DOCK_COLOR}" stroke-width="{sw:.0f}"/>'
        )

    # 7. Dock marker
    dx, dy = to_svg(0, 0)
    elements.append(
        f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="{dock_r:.0f}" '
        f'fill="{_DOCK_COLOR}" stroke="#333" stroke-width="{sw:.0f}"/>'
    )
    elements.append(
        f'<text x="{dx:.0f}" y="{dy:.0f}" text-anchor="middle" '
        f'dominant-baseline="middle" font-size="{dock_r:.0f}" fill="#333" '
        f'font-weight="bold" font-family="sans-serif">⌂</text>'
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
                            f'r="{dock_r*0.7:.0f}" fill="{_MOWER_COLOR}" '
                            f'stroke="white" stroke-width="{sw:.0f}"/>'
                        )
            except Exception:
                pass

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">'
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="{_BACKGROUND}"/>'
        + "".join(elements)
        + "</svg>"
    )


# Legacy stub for compatibility
def render_mower_map(map_subsets: list[Any], positions: list[Any] | None = None) -> str | None:
    """Legacy renderer — not used for mowers."""
    return None
