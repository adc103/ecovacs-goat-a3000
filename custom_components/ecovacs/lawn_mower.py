"""Ecovacs mower entity."""

import logging
from typing import Any

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

    # ---- Standard lawn mower actions ----

    async def async_start_mowing(self) -> None:
        """Start auto mowing."""
        await self._clean_command(CleanAction.START)

    async def async_pause(self) -> None:
        """Pause the mower."""
        await self._clean_command(CleanAction.PAUSE)

    async def async_dock(self) -> None:
        """Return mower to dock."""
        await self._device.execute_command(self._capability.charge.execute())

    # ---- Zone mowing services ----

    async def async_mow_zone(self, zone_id: str) -> None:
        """Start mowing a specific zone (spotArea)."""
        import deebot_client.commands.json.clean as clean_module
        cmd = clean_module.CleanMowerArea(CleanMode.SPOT_AREA, [int(zone_id)])
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started zone mowing for zone %s", zone_id)

    async def async_mow_edge(self, zone_id: str) -> None:
        """Start edge mowing for a specific zone (border)."""
        import deebot_client.commands.json.clean as clean_module
        cmd = clean_module.CleanMowerArea.__new__(clean_module.CleanMowerArea)
        cmd._additional_content = {"type": "border", "value": f"aid:{zone_id}"}
        clean_module.CleanMower.__init__(cmd, CleanAction.START)
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started edge mowing for zone %s", zone_id)

    async def async_mow_enhanced(self, zone_id: str) -> None:
        """Start enhanced mowing for a specific zone (assart)."""
        import deebot_client.commands.json.clean as clean_module
        cmd = clean_module.CleanMowerArea.__new__(clean_module.CleanMowerArea)
        cmd._additional_content = {"type": "assart", "value": zone_id}
        clean_module.CleanMower.__init__(cmd, CleanAction.START)
        await self._device.execute_command(cmd)
        _LOGGER.debug("Started enhanced mowing for zone %s", zone_id)

    # ---- Settings services ----

    async def async_set_rain_delay(self, enable: bool, delay_minutes: int = 180) -> None:
        """Enable or disable rain delay."""
        from .mower_services import SetRainDelay
        await self._device.execute_command(SetRainDelay(enable, delay_minutes))
        _LOGGER.debug("Set rain delay: enable=%s delay=%s", enable, delay_minutes)

    async def async_set_anim_protect(
        self, enable: bool, start_time: str = "21:0", end_time: str = "6:0"
    ) -> None:
        """Set animal protection window."""
        from .mower_services import SetAnimProtect
        await self._device.execute_command(SetAnimProtect(enable, start_time, end_time))
        _LOGGER.debug("Set animal protection: enable=%s %s-%s", enable, start_time, end_time)

    async def async_set_cut_height(self, level: int) -> None:
        """Set cut height level (1-5)."""
        from .mower_services import SetCutHeight
        await self._device.execute_command(SetCutHeight(level))
        _LOGGER.debug("Set cut height: level=%s", level)

    async def async_set_cut_efficiency(self, level: int) -> None:
        """Set cut efficiency level (1-3)."""
        from .mower_services import SetCutEfficiency
        await self._device.execute_command(SetCutEfficiency(level))
        _LOGGER.debug("Set cut efficiency: level=%s", level)

    async def async_set_obstacle_height(self, level: int) -> None:
        """Set obstacle detection height sensitivity (1-3)."""
        from .mower_services import SetObstacleHeight
        await self._device.execute_command(SetObstacleHeight(level))
        _LOGGER.debug("Set obstacle height: level=%s", level)

    async def async_set_video_camera(self, enable: bool) -> None:
        """Enable or disable the video camera."""
        from .mower_services import SetVideoCamera
        await self._device.execute_command(SetVideoCamera(enable))
        _LOGGER.debug("Set video camera: enable=%s", enable)

    # ---- Info services (with response) ----

    async def async_get_zone_parameters(self) -> dict[str, Any]:
        """Get per-zone parameters (height, cut mode, obstacle height)."""
        from .mower_services import GetAreaParameter
        result = await self._device.execute_command(GetAreaParameter())
        return result or {}

    async def async_get_zone_mow_duration(self, zone_id: str = "0") -> dict[str, Any]:
        """Get total mow duration for a zone in seconds."""
        from .mower_services import GetAreasMowDuration
        result = await self._device.execute_command(GetAreasMowDuration(zone_id))
        return result or {}
