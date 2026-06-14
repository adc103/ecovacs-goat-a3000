"""Ecovacs mower entity."""

import logging

from deebot_client.capabilities import Capabilities, DeviceType
from deebot_client.device import Device
from deebot_client.events import StateEvent
from deebot_client.models import CleanAction, CleanMode, State

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityEntityDescription,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsConfigEntry
from .entity import EcovacsEntity

_LOGGER = logging.getLogger(__name__)


_STATE_TO_MOWER_STATE = {
    State.IDLE: LawnMowerActivity.PAUSED,
    State.CLEANING: LawnMowerActivity.MOWING,
    State.RETURNING: LawnMowerActivity.RETURNING,
    State.DOCKED: LawnMowerActivity.DOCKED,
    State.ERROR: LawnMowerActivity.ERROR,
    State.PAUSED: LawnMowerActivity.PAUSED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ecovacs mowers."""
    controller = config_entry.runtime_data
    mowers: list[EcovacsMower] = [
        EcovacsMower(device)
        for device in controller.devices
        if device.capabilities.device_type is DeviceType.MOWER
    ]
    _LOGGER.debug("Adding Ecovacs Mowers to Home Assistant: %s", mowers)
    async_add_entities(mowers)


class EcovacsMower(
    EcovacsEntity[Capabilities],
    LawnMowerEntity,
):
    """Ecovacs Mower."""

    _attr_supported_features = (
        LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
    )

    entity_description = LawnMowerEntityEntityDescription(key="mower", name=None)

    def __init__(self, device: Device) -> None:
        """Initialize the mower."""
        super().__init__(device, device.capabilities)

    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()

        async def on_status(event: StateEvent) -> None:
            self._attr_activity = _STATE_TO_MOWER_STATE[event.state]
            self.async_write_ha_state()

        self._subscribe(self._capability.state.event, on_status)

    async def _clean_command(self, action: CleanAction) -> None:
        await self._device.execute_command(
            self._capability.clean.action.command(action)
        )

    async def async_start_mowing(self) -> None:
        """Start auto mowing."""
        await self._clean_command(CleanAction.START)

    async def async_pause(self) -> None:
        """Pause the mower."""
        await self._clean_command(CleanAction.PAUSE)

    async def async_dock(self) -> None:
        """Return mower to dock."""
        await self._device.execute_command(self._capability.charge.execute())

    async def async_mow_zone(self, zone_id: str) -> None:
        """Start mowing a specific zone (spotArea)."""
        import deebot_client.commands.json.clean as clean_module
        cmd = clean_module.CleanMowerArea(
            CleanMode.SPOT_AREA, [int(zone_id)]
        )
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started zone mowing for zone %s", zone_id)

    async def async_mow_edge(self, zone_id: str) -> None:
        """Start edge mowing for a specific zone (border)."""
        import deebot_client.commands.json.clean as clean_module
        # border mode uses a string value like "aid:2"
        cmd = clean_module.CleanMowerArea.__new__(clean_module.CleanMowerArea)
        cmd._additional_content = {
            "type": "border",
            "value": f"aid:{zone_id}",
        }
        clean_module.CleanMower.__init__(cmd, CleanAction.START)
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started edge mowing for zone %s", zone_id)

    async def async_mow_enhanced(self, zone_id: str) -> None:
        """Start enhanced mowing for a specific zone (assart)."""
        import deebot_client.commands.json.clean as clean_module
        cmd = clean_module.CleanMowerArea.__new__(clean_module.CleanMowerArea)
        cmd._additional_content = {
            "type": "assart",
            "value": zone_id,
        }
        clean_module.CleanMower.__init__(cmd, CleanAction.START)
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started enhanced mowing for zone %s", zone_id)
