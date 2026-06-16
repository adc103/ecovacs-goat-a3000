"""Sensor exposing live mow state from onStats/onCleanInfo/onChargeState."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=5)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    from .controller import EcovacsController
    controller: EcovacsController = entry.runtime_data
    entities = []
    for device in controller.devices:
        device_id = getattr(device, 'device_id', 'mower')
        name = getattr(device.device_info, 'nick', device_id) if hasattr(device, 'device_info') else device_id
        entities.append(MowStateSensor(hass, device_id, name))
    if entities:
        async_add_entities(entities, True)


class MowStateSensor(SensorEntity):
    """Sensor that exposes live mow state as attributes."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, device_id: str, name: str) -> None:
        self._hass = hass
        self._device_id = device_id
        self._clean_name = name.lower().replace(' ', '_')
        self._attr_unique_id = f"{device_id}_mow_state"
        self._attr_name = "Mow State"
        self._attr_icon = "mdi:robot-mower"
        self._unsub = None

    @property
    def device_info(self):
        return {"identifiers": {("ecovacs", self._device_id)}}

    async def async_added_to_hass(self) -> None:
        self._unsub = async_track_time_interval(
            self._hass, self._update, SCAN_INTERVAL
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _update(self, _now=None) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        from .patches import get_mow_state
        s = get_mow_state()
        motion = s.get('motion_state')
        if s.get('is_charging') and motion == 'pause':
            return 'charging_to_resume'
        return motion or 'unknown'

    @property
    def extra_state_attributes(self) -> dict:
        from .patches import get_mow_state
        s = get_mow_state()
        attrs = dict(s)
        # Add computed fields
        mowed = s.get('mowed_area_m2', 0)
        total = s.get('total_area_m2', 0)
        if total:
            attrs['progress_pct'] = round(mowed / total * 100)
        secs = s.get('mow_time_s', 0)
        if secs:
            attrs['mow_time_human'] = f"{secs // 3600}h {(secs % 3600) // 60}m"
        return attrs
