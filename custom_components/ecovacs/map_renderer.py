"""SVG map renderer for GOAT A3000 LiDAR mower.

Renders zone polygon data received via onMI MQTT messages into an SVG
suitable for display in Home Assistant's image entity.

The Rust map module (MapDataRs) in deebot_client is designed for vacuum
pixel maps and returns None for mowers which use polygon-only zone data.
This renderer provides mower-specific SVG generation from MapSubsetEvent data.

Zone type mapping (from MapSetType):
- ROOMS (ar): Mowing zones — rendered as green fills
- VIRTUAL_WALLS (vw): Virtual walls — rendered as red lines
- NO_MOP_ZONES (mw): No-go zones — rendered as red hatched fills
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Zone colors
_ZONE_COLORS = [
    ("#4a9eff", "#2d7acc"),   # blue
    ("#4aff7b", "#2dcc5a"),   # green
    ("#ff9f4a", "#cc7a2d"),   # orange
    ("#c84aff", "#9b2dcc"),   # purple
    ("#ffee4a", "#ccbb2d"),   # yellow
    ("#ff6b6b", "#cc4444"),   # red
]

_NO_GO_COLOR = ("#ff4444", "#cc2222")
_VIRTUAL_WALL_COLOR = "#ff2222"
_BACKGROUND_COLOR = "#0d1f0d"
_DOCK_COLOR = "#ffe605"
_PATH_COLOR = "#ffffff"


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


def render_mower_map(
    map_subsets: list[Any],
    positions: list[Any] | None = None,
    trace_points: list[str] | None = None,
) -> str | None:
    """Render mower zone map as SVG string.

    Args:
        map_subsets: List of MapSubsetEvent objects
        positions: List of Position objects (mower + charger locations)
        trace_points: List of mowing path trace strings

    Returns:
        SVG string or None if no data to render
    """
    if not map_subsets:
        return None

    # Separate zones by type
    mow_zones: dict[int, list[tuple[int, int]]] = {}
    no_go_zones: list[list[tuple[int, int]]] = []
    virtual_walls: list[list[tuple[int, int]]] = []

    try:
        from deebot_client.events.map import MapSetType
        ROOMS = MapSetType.ROOMS
        NO_MOP = MapSetType.NO_MOP_ZONES
        VIRTUAL = MapSetType.VIRTUAL_WALLS
    except Exception:
        ROOMS = "ar"
        NO_MOP = "mw"
        VIRTUAL = "vw"

    for subset in map_subsets:
        coords_str = getattr(subset, "coordinates", "") or ""
        if not coords_str:
            continue

        points = _parse_coords(coords_str)
        if len(points) < 3:
            continue

        set_type = getattr(subset, "type", None)
        zone_id = getattr(subset, "id", 0)

        if set_type == ROOMS or str(set_type) == "ar":
            # Keep best (most detailed) polygon per zone ID
            if zone_id not in mow_zones or len(points) > len(mow_zones[zone_id]):
                mow_zones[zone_id] = points
        elif set_type == NO_MOP or str(set_type) == "mw":
            no_go_zones.append(points)
        elif set_type == VIRTUAL or str(set_type) == "vw":
            virtual_walls.append(points)

    if not mow_zones and not no_go_zones:
        return None

    # Compute bounds from all points
    all_x: list[int] = []
    all_y: list[int] = []

    for pts in mow_zones.values():
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)
    for pts in no_go_zones:
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)
    for pts in virtual_walls:
        all_x.extend(p[0] for p in pts)
        all_y.extend(p[1] for p in pts)

    # Include dock at origin
    all_x.append(0)
    all_y.append(0)

    if not all_x:
        return None

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    span = max(max_x - min_x, max_y - min_y)
    pad = max(span * 0.05, 1000)  # at least 1m padding

    svg_w = max_x - min_x + pad * 2
    svg_h = max_y - min_y + pad * 2

    def to_svg(x: int, y: int) -> tuple[float, float]:
        """Convert mm coordinates to SVG coordinates (flip Y axis)."""
        return (x - min_x + pad, max_y - y + pad)

    def pts_to_poly(points: list[tuple[int, int]]) -> str:
        return " ".join(f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in points))

    elements: list[str] = []
    stroke_w = max(svg_w, svg_h) * 0.002

    # Render mowing zones
    for i, (zone_id, pts) in enumerate(sorted(mow_zones.items())):
        fill, stroke = _ZONE_COLORS[i % len(_ZONE_COLORS)]
        poly = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{poly}" '
            f'fill="{fill}" fill-opacity="0.35" '
            f'stroke="{stroke}" stroke-width="{stroke_w:.0f}"/>'
        )
        # Zone label at centroid
        svg_pts = [to_svg(x, y) for x, y in pts]
        cx = sum(p[0] for p in svg_pts) / len(svg_pts)
        cy = sum(p[1] for p in svg_pts) / len(svg_pts)
        font_size = max(svg_w, svg_h) * 0.025
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-size="{font_size:.0f}" fill="white" '
            f'font-weight="bold" font-family="sans-serif">'
            f'Zone {zone_id}</text>'
        )

    # Render no-go zones (hatched red)
    for pts in no_go_zones:
        fill, stroke = _NO_GO_COLOR
        poly = pts_to_poly(pts)
        elements.append(
            f'<polygon points="{poly}" '
            f'fill="{fill}" fill-opacity="0.4" '
            f'stroke="{stroke}" stroke-width="{stroke_w:.0f}" '
            f'stroke-dasharray="{stroke_w*3:.0f}"/>'
        )

    # Render virtual walls (red lines)
    for pts in virtual_walls:
        if len(pts) >= 2:
            sx1, sy1 = to_svg(*pts[0])
            sx2, sy2 = to_svg(*pts[-1])
            elements.append(
                f'<line x1="{sx1:.0f}" y1="{sy1:.0f}" '
                f'x2="{sx2:.0f}" y2="{sy2:.0f}" '
                f'stroke="{_VIRTUAL_WALL_COLOR}" stroke-width="{stroke_w*2:.0f}"/>'
            )

    # Render mowing path traces
    if trace_points:
        path_data: list[str] = []
        for trace in trace_points:
            pts = _parse_coords(trace)
            if not pts:
                continue
            svg_pts = [to_svg(x, y) for x, y in pts]
            cmd = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in svg_pts)
            path_data.append(cmd)
        if path_data:
            elements.append(
                f'<path d="{" ".join(path_data)}" '
                f'fill="none" stroke="{_PATH_COLOR}" '
                f'stroke-width="{stroke_w*0.5:.0f}" '
                f'stroke-opacity="0.6"/>'
            )

    # Render positions (dock + mower)
    dock_r = max(svg_w, svg_h) * 0.012
    dx, dy = to_svg(0, 0)
    elements.append(
        f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="{dock_r:.0f}" '
        f'fill="{_DOCK_COLOR}" stroke="#333" stroke-width="{stroke_w:.0f}"/>'
    )

    if positions:
        for pos in positions:
            try:
                px = getattr(pos, "x", None)
                py = getattr(pos, "y", None)
                pos_type = str(getattr(pos, "type", "")).lower()
                if px is not None and py is not None and "deebot" in pos_type:
                    sx, sy = to_svg(int(px), int(py))
                    elements.append(
                        f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="{dock_r:.0f}" '
                        f'fill="#00aaff" stroke="white" stroke-width="{stroke_w:.0f}"/>'
                    )
            except Exception:
                pass

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">'
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="{_BACKGROUND_COLOR}"/>'
        + "".join(elements)
        + "</svg>"
    )

    return svg
