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
        if svg := self._map.get_svg_map():
            return svg.encode()

        return None

    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()

        async def on_info(event: CachedMapInfoEvent) -> None:
            for map_obj in event.maps:
                if map_obj.using:
                    self._attr_extra_state_attributes["map_name"] = map_obj.name

        async def on_changed(event: MapChangedEvent) -> None:
            self._attr_image_last_updated = event.when
            self.async_write_ha_state()

        self._subscribe(self._capability.cached_info.event, on_info)
        self._subscribe(self._capability.changed.event, on_changed)

    async def async_update(self) -> None:
        """Update the entity.

        Only used by the generic entity update service.
        """
        await super().async_update()
        self._map.refresh()
