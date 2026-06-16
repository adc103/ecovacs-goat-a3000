import logging
"""Ecovacs image entities."""

from typing import cast

from deebot_client.capabilities import CapabilityMap
from deebot_client.device import Device
from deebot_client.events.map import CachedMapInfoEvent, MapChangedEvent
from deebot_client.map import Map

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsConfigEntry
from .entity import EcovacsEntity


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add entities for passed config_entry in HA."""
    controller = config_entry.runtime_data
    _LOGGER.warning("image.py: setting up, %d devices found", len(controller.devices))
    entities = []
    for device in controller.devices:
        caps = device.capabilities.map
        _LOGGER.warning("image.py: device %s has map capability: %s", 
                       device.device_info.get("nick"), caps is not None)
        if caps:
            if device.map is None:
                _LOGGER.warning("image.py: device.map is None despite map capability!")
            else:
                _LOGGER.warning("image.py: creating EcovacsMap entity")
                entities.append(EcovacsMap(device, caps, hass))

    _LOGGER.warning("image.py: creating %d map entities", len(entities))
    if entities:
        async_add_entities(entities)


class EcovacsMap(
    EcovacsEntity[CapabilityMap],
    ImageEntity,
):
    """Ecovacs map."""

    _attr_content_type = "image/svg+xml"

    def __init__(
        self,
        device: Device,
        capability: CapabilityMap,
        hass: HomeAssistant,
    ) -> None:
        """Initialize entity."""
        # ImageEntity.__init__ does not call super().__init__() so we must
        # call both parent inits explicitly to avoid breaking the MRO chain
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{device.device_info['did']}_{self.entity_description.key}"
        self._device = device
        self._capability = capability
        self._subscribed_events: set = set()
        self._attr_extra_state_attributes = {}
        self._map = cast(Map, self._device.map)
        self._attr_has_entity_name = True
        self._attr_should_poll = False

    entity_description = EntityDescription(
        key="map",
        translation_key="map",
    )

    def image(self) -> bytes | None:
        """Return bytes of image or None."""
        from deebot_client.capabilities import DeviceType
        from .map_renderer import render_mower_map_from_store

        # For mowers, use our Python renderer which handles polygon zone data
        # The Rust map module returns None for mowers (it's designed for vacuum pixel maps)
        if self._device.capabilities.device_type is DeviceType.MOWER:
            # Get zones from our _zone_store (map_data.map_subsets ignores ROOMS type)
            from custom_components.ecovacs.patches import (
                get_zone_store, get_path_store,
                get_obstacle_store, get_dock_store,
                get_trace_store, get_trace_store_svg, get_mower_heading,
            )
            mid = "1"
            zone_store     = get_zone_store(mid)
            path_store     = get_path_store(mid)
            obstacle_store = get_obstacle_store(mid)
            dock_store     = get_dock_store(mid)
            trace_svg      = get_trace_store_svg()
            pos_trace      = get_trace_store()
            heading        = get_mower_heading()
            positions      = self._map._map_data._positions

            # Prefer onMapTrace polygons; fall back to onPos polyline
            if trace_svg:
                trace_points = trace_svg
            elif pos_trace:
                trace_points = [";".join(f"{x},{y}" for x, y, _ in pos_trace)]
            else:
                trace_points = None

            _LOGGER.warning(
                "image(): zones=%d paths=%d obstacles=%d trace_svg=%d pos=%d heading=%d",
                len(zone_store), len(path_store), len(obstacle_store),
                len(trace_svg), len(pos_trace), heading,
            )

            svg = render_mower_map_from_store(
                zone_store,
                positions,
                path_store=path_store,
                obstacle_store=obstacle_store,
                dock_outline_store=dock_store,
                trace_points=trace_points,
                mower_heading=heading,
            )
            if svg:
                _LOGGER.warning("image(): rendered SVG (%d chars)", len(svg))
                return svg.encode()
            else:
                _LOGGER.warning("image(): no zone data yet")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose mow state so the Lovelace card can read it."""
        try:
            from custom_components.ecovacs.patches import get_mow_state, get_mower_heading  # noqa: PLC0415
            state = dict(get_mow_state())
            state['heading'] = get_mower_heading()
            mowed = state.get('mowed_area_m2', 0)
            total = state.get('total_area_m2', 0)
            if total:
                state['progress_pct'] = round(mowed / total * 100)
            secs = state.get('mow_time_s', 0)
            if secs:
                state['mow_time_human'] = f"{secs // 3600}h {(secs % 3600) // 60}m"
            return state
        except Exception:
            return {}
        else:
            # Vacuum: use Rust map module
            svg = self._map.get_svg_map()
            if svg:
                return svg.encode()

        # Placeholder when no map data yet
        placeholder = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#1a1a2e"/><text x="200" y="180" font-family="sans-serif" font-size="16" fill="#4a9eff" text-anchor="middle">GOAT A3000 LiDAR</text><text x="200" y="210" font-family="sans-serif" font-size="14" fill="#888" text-anchor="middle">Map will appear after mowing</text></svg>'
        return placeholder.encode()

    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()

        async def on_info(event: CachedMapInfoEvent) -> None:
            for map_obj in event.maps:
                if map_obj.using:
                    self._attr_extra_state_attributes["map_name"] = map_obj.name

        async def on_changed(event: MapChangedEvent) -> None:
            _LOGGER.warning("MapChangedEvent received in image entity - clearing cache and updating")
            self._attr_image_last_updated = event.when
            # Clear the cached image so async_image() fetches fresh bytes
            self._cached_image = None
            self.async_write_ha_state()

        self._subscribe(self._capability.cached_info.event, on_info)
        self._subscribe(self._capability.changed.event, on_changed)
        _LOGGER.warning("Image entity subscribed to MapChangedEvent successfully")

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        await super().async_update()
        self._map.refresh()
