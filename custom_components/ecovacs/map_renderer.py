"""SVG map renderer for GOAT A3000 LiDAR mower.

Renders zone polygon data received via onMI/onArI MQTT messages into an SVG
suitable for display in Home Assistant's image entity.

Zone numbering from getAreaSet data:
- Zones with many points = mowing areas
- Small zones / specific patterns = no-go zones or virtual walls

Coordinates are in mm from dock position (dock = 0,0).
Y axis is flipped for SVG (SVG Y increases downward, map Y increases upward).
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Zone fill colors (fill, stroke) - cycling for multiple zones
_ZONE_COLORS = [
    ("#1a6b3a", "#2dcc5a"),   # green
    ("#1a4a7a", "#4a9eff"),   # blue
    ("#7a4a1a", "#cc7a2d"),   # orange
    ("#4a1a7a", "#9b2dcc"),   # purple
    ("#6b6b1a", "#ccbb2d"),   # yellow
]

_NO_GO_COLOR = ("#7a0000", "#ff4444")
_VIRTUAL_WALL_COLOR = "#ff2222"
_BACKGROUND_COLOR = "#0d1f0d"
_DOCK_COLOR = "#ffe605"
_MOWER_COLOR = "#00aaff"
_PATH_COLOR = "rgba(255,255,255,0.5)"

# Zones smaller than this point count are likely virtual walls or markers
_MIN_ZONE_POINTS = 20


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


def render_mower_map_from_store(
    zone_store: dict[int, str],
    positions: list[Any] | None = None,
    trace_points: list[str] | None = None,
) -> str | None:
    """Render mower map from zone_store dict {zone_id: coordinates_str}.

    zone_store is populated by the OnMI/onArI MQTT handlers.
    """
    if not zone_store:
        return None

    # Parse all zones
    all_x: list[int] = []
    all_y: list[int] = []
    zone_polygons: dict[int, list[tuple[int, int]]] = {}

    for zone_id, coords_str in zone_store.items():
        points = _parse_coords(coords_str)
        if len(points) < 3:
            continue
        zone_polygons[zone_id] = points
        all_x.extend(p[0] for p in points)
        all_y.extend(p[1] for p in points)

    if not zone_polygons:
        return None

    # Include dock at origin
    all_x.append(0)
    all_y.append(0)

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    span = max(max_x - min_x, max_y - min_y)
    pad = max(span * 0.04, 1000)

    svg_w = max_x - min_x + pad * 2
    svg_h = max_y - min_y + pad * 2

    stroke_w = max(svg_w, svg_h) * 0.0015
    font_size = max(svg_w, svg_h) * 0.022
    dock_r = max(svg_w, svg_h) * 0.014

    def to_svg(x: int, y: int) -> tuple[float, float]:
        """Convert mm coordinates to SVG (flip Y axis)."""
        return (x - min_x + pad, max_y - y + pad)

    def pts_to_poly(points: list[tuple[int, int]]) -> str:
        return " ".join(f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in points))

    elements: list[str] = []
    color_idx = 0

    # Separate large zones (mowing areas) from small ones (no-go / virtual walls)
    mow_zones = {zid: pts for zid, pts in sorted(zone_polygons.items()) if len(pts) >= _MIN_ZONE_POINTS}
    small_zones = {zid: pts for zid, pts in sorted(zone_polygons.items()) if len(pts) < _MIN_ZONE_POINTS}

    # Render mowing zones
    for zone_id, pts in mow_zones.items():
        fill, stroke = _ZONE_COLORS[color_idx % len(_ZONE_COLORS)]
        color_idx += 1
        poly = pts_to_poly(pts)

        elements.append(
            f'<polygon points="{poly}" '
            f'fill="{fill}" fill-opacity="0.7" '
            f'stroke="{stroke}" stroke-width="{stroke_w:.0f}"/>'
        )

        # Zone label at centroid
        svg_pts = [to_svg(x, y) for x, y in pts]
        cx = sum(p[0] for p in svg_pts) / len(svg_pts)
        cy = sum(p[1] for p in svg_pts) / len(svg_pts)
        elements.append(
            f'<text x="{cx:.0f}" y="{cy:.0f}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-size="{font_size:.0f}" fill="white" '
            f'font-weight="bold" font-family="sans-serif" '
            f'opacity="0.9">Zone {zone_id}</text>'
        )

    # Render small zones as virtual walls (lines)
    for zone_id, pts in small_zones.items():
        if len(pts) >= 2:
            # Draw as line
            line_pts = " ".join(
                f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in pts)
            )
            elements.append(
                f'<polyline points="{line_pts}" '
                f'fill="none" stroke="{_VIRTUAL_WALL_COLOR}" '
                f'stroke-width="{stroke_w * 3:.0f}" stroke-linecap="round"/>'
            )

    # Render mowing path traces
    if trace_points:
        for trace in trace_points:
            pts = _parse_coords(trace)
            if len(pts) < 2:
                continue
            svg_pts_str = " ".join(f"{sx:.0f},{sy:.0f}" for sx, sy in (to_svg(x, y) for x, y in pts))
            elements.append(
                f'<polyline points="{svg_pts_str}" '
                f'fill="none" stroke="{_PATH_COLOR}" '
                f'stroke-width="{stroke_w * 0.6:.0f}"/>'
            )

    # Dock marker (yellow circle at origin)
    dx, dy = to_svg(0, 0)
    elements.append(
        f'<circle cx="{dx:.0f}" cy="{dy:.0f}" r="{dock_r:.0f}" '
        f'fill="{_DOCK_COLOR}" stroke="#333" stroke-width="{stroke_w:.0f}" opacity="0.95"/>'
    )
    elements.append(
        f'<text x="{dx:.0f}" y="{dy:.0f}" '
        f'text-anchor="middle" dominant-baseline="middle" '
        f'font-size="{dock_r * 1.2:.0f}" fill="#333" font-weight="bold" '
        f'font-family="sans-serif">⌂</text>'
    )

    # Mower position (blue dot)
    if positions:
        for pos in positions:
            try:
                px = getattr(pos, "x", None)
                py = getattr(pos, "y", None)
                pos_type = str(getattr(pos, "type", "")).lower()
                if px is not None and py is not None and "deebot" in pos_type:
                    sx, sy = to_svg(int(px), int(py))
                    # Don't draw mower if it's at dock position (0,0) - it's docked
                    if int(px) != 0 or int(py) != 0:
                        elements.append(
                            f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="{dock_r * 0.7:.0f}" '
                            f'fill="{_MOWER_COLOR}" stroke="white" '
                            f'stroke-width="{stroke_w:.0f}" opacity="0.95"/>'
                        )
            except Exception:
                pass

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_w:.0f} {svg_h:.0f}">'
        f'<rect width="{svg_w:.0f}" height="{svg_h:.0f}" fill="{_BACKGROUND_COLOR}"/>'
        + "".join(elements)
        + "</svg>"
    )


# Keep old function for compatibility
def render_mower_map(
    map_subsets: list[Any],
    positions: list[Any] | None = None,
) -> str | None:
    """Legacy renderer using MapSubsetEvent list (not used for mowers)."""
    return None
