"""Patches for GOAT A3000 LiDAR (cr0e4u) support.

This module monkey-patches the deebot_client library to:
1. Fix cr0e4u hardware definition (correct commands, life span, map support)
2. Add CleanMower and CleanMowerArea commands
"""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def apply_patches() -> None:
    """Apply all patches to deebot_client."""
    _patch_clean_commands()
    _patch_get_map_set_p2p()
    _patch_on_mi_handler()
    _patch_cr0e4u()
    _LOGGER.info("GOAT A3000 patches applied successfully")


def _patch_clean_commands() -> None:
    """Add CleanMower and CleanMowerArea to deebot_client.commands.json.clean."""
    from deebot_client.commands.json.clean import Clean
    from deebot_client.models import CleanAction, CleanMode
    import deebot_client.commands.json.clean as clean_module

    class CleanMower(Clean):
        """Clean command for mower devices.

        Uses 'clean' endpoint with V2-style content format.
        Confirmed via traffic analysis of GOAT A3000 LiDAR (cr0e4u).
        """

        def _get_args(self, action: CleanAction) -> dict[str, Any]:
            content: dict[str, str] = {}
            args = {"act": action.value, "content": content}
            match action:
                case CleanAction.START:
                    content["type"] = CleanMode.AUTO.value
                case CleanAction.STOP | CleanAction.PAUSE:
                    content["type"] = ""
            return args

    class CleanMowerArea(CleanMower):
        """Clean area command for mower devices.

        Supports spotArea (zone), border (edge), assart (enhanced) mowing.
        Confirmed via traffic analysis of GOAT A3000 LiDAR (cr0e4u).
        """

        def __init__(
            self, mode: CleanMode, area: list[int | float], _: int = 1
        ) -> None:
            self._additional_content = {
                "type": mode.value,
                "value": ",".join(str(i) for i in area),
            }
            super().__init__(CleanAction.START)

        def _get_args(self, action: CleanAction) -> dict[str, Any]:
            args = super()._get_args(action)
            if action == CleanAction.START:
                args["content"].update(self._additional_content)
            return args

    clean_module.CleanMower = CleanMower
    clean_module.CleanMowerArea = CleanMowerArea
    _LOGGER.debug("CleanMower and CleanMowerArea patched")


def _patch_cr0e4u() -> None:
    """Patch cr0e4u hardware definition for GOAT A3000 LiDAR."""
    import deebot_client.hardware.cr0e4u as cr0e4u_module
    from deebot_client.capabilities import (
        Capabilities,
        CapabilityClean,
        CapabilityCleanAction,
        CapabilityCustomCommand,
        CapabilityEvent,
        CapabilityExecute,
        CapabilityLifeSpan,
        CapabilityMap,
        CapabilitySet,
        CapabilitySetEnable,
        CapabilitySettings,
        CapabilityStats,
        DeviceType,
    )
    from deebot_client.commands.json.map import SetMajorMap
    from deebot_client.commands.json import (
        GetBorderSwitch,
        GetChildLock,
        GetCrossMapBorderWarning,
        GetCutDirection,
        GetMoveUpWarning,
        GetSafeProtect,
        SetBorderSwitch,
        SetChildLock,
        SetCrossMapBorderWarning,
        SetCutDirection,
        SetMoveUpWarning,
        SetSafeProtect,
    )
    from deebot_client.commands.json.advanced_mode import GetAdvancedMode, SetAdvancedMode
    from deebot_client.commands.json.battery import GetBattery
    from deebot_client.commands.json.charge import Charge
    from deebot_client.commands.json.charge_state import GetChargeState
    from deebot_client.commands.json.clean import GetCleanInfo
    from deebot_client.commands.json.custom import CustomCommand
    from deebot_client.commands.json.error import GetError
    from deebot_client.commands.json.life_span import GetLifeSpan, ResetLifeSpan
    from deebot_client.commands.json.map import GetCachedMapInfo, GetMajorMap, GetMinorMap, GetMapSet, GetMapTrace
    from deebot_client.commands.json.network import GetNetInfo
    from deebot_client.commands.json.play_sound import PlaySound
    from deebot_client.commands.json.pos import GetPos
    from deebot_client.commands.json.stats import GetStats, GetTotalStats
    from deebot_client.commands.json.volume import GetVolume, SetVolume
    from deebot_client.const import DataType
    from deebot_client.events import (
        AdvancedModeEvent,
        AvailabilityEvent,
        BatteryEvent,
        BorderSwitchEvent,
        CachedMapInfoEvent,
        ChildLockEvent,
        CrossMapBorderWarningEvent,
        CustomCommandEvent,
        CutDirectionEvent,
        ErrorEvent,
        LifeSpan,
        LifeSpanEvent,
        MajorMapEvent,
        MapChangedEvent,
        MapTraceEvent,
        MoveUpWarningEvent,
        NetworkInfoEvent,
        PositionsEvent,
        ReportStatsEvent,
        RoomsEvent,
        SafeProtectEvent,
        StateEvent,
        StatsEvent,
        TotalStatsEvent,
        VolumeEvent,
    )
    from deebot_client.models import StaticDeviceInfo
    import deebot_client.commands.json.clean as clean_module

    CleanMower = clean_module.CleanMower
    CleanMowerArea = clean_module.CleanMowerArea

    def get_device_info() -> StaticDeviceInfo:
        """Get device info for GOAT A3000 LiDAR."""
        return StaticDeviceInfo(
            DataType.JSON,
            Capabilities(
                device_type=DeviceType.MOWER,
                availability=CapabilityEvent(
                    AvailabilityEvent, [GetBattery(is_available_check=True)]
                ),
                battery=CapabilityEvent(BatteryEvent, [GetBattery()]),
                charge=CapabilityExecute(Charge),
                clean=CapabilityClean(
                    action=CapabilityCleanAction(
                        command=CleanMower, area=CleanMowerArea
                    ),
                ),
                custom=CapabilityCustomCommand(
                    event=CustomCommandEvent, get=[], set=CustomCommand
                ),
                error=CapabilityEvent(ErrorEvent, [GetError()]),
                life_span=CapabilityLifeSpan(
                    types=(LifeSpan.BLADE,),
                    event=LifeSpanEvent,
                    get=[GetLifeSpan([LifeSpan.BLADE])],
                    reset=ResetLifeSpan,
                ),
                map=CapabilityMap(
                    cached_info=CapabilityEvent(
                        CachedMapInfoEvent, [GetCachedMapInfo()]
                    ),
                    changed=CapabilityEvent(MapChangedEvent, []),
                    major=CapabilitySet(MajorMapEvent, [GetMajorMap()], SetMajorMap),
                    minor=CapabilityExecute(GetMinorMap),
                    position=CapabilityEvent(PositionsEvent, [GetPos()]),
                    rooms=CapabilityEvent(RoomsEvent, [GetCachedMapInfo()]),
                    set=CapabilityExecute(GetMapSet),
                    trace=CapabilityEvent(MapTraceEvent, [GetMapTrace()]),
                ),
                network=CapabilityEvent(NetworkInfoEvent, [GetNetInfo()]),
                play_sound=CapabilityExecute(PlaySound),
                settings=CapabilitySettings(
                    advanced_mode=CapabilitySetEnable(
                        AdvancedModeEvent, [GetAdvancedMode()], SetAdvancedMode
                    ),
                    border_switch=CapabilitySetEnable(
                        BorderSwitchEvent, [GetBorderSwitch()], SetBorderSwitch
                    ),
                    cut_direction=CapabilitySet(
                        CutDirectionEvent, [GetCutDirection()], SetCutDirection
                    ),
                    child_lock=CapabilitySetEnable(
                        ChildLockEvent, [GetChildLock()], SetChildLock
                    ),
                    moveup_warning=CapabilitySetEnable(
                        MoveUpWarningEvent, [GetMoveUpWarning()], SetMoveUpWarning
                    ),
                    cross_map_border_warning=CapabilitySetEnable(
                        CrossMapBorderWarningEvent,
                        [GetCrossMapBorderWarning()],
                        SetCrossMapBorderWarning,
                    ),
                    safe_protect=CapabilitySetEnable(
                        SafeProtectEvent, [GetSafeProtect()], SetSafeProtect
                    ),
                    volume=CapabilitySet(VolumeEvent, [GetVolume()], SetVolume),
                ),
                state=CapabilityEvent(
                    StateEvent, [GetChargeState(), GetCleanInfo()]
                ),
                stats=CapabilityStats(
                    clean=CapabilityEvent(StatsEvent, [GetStats()]),
                    report=CapabilityEvent(ReportStatsEvent, []),
                    total=CapabilityEvent(TotalStatsEvent, [GetTotalStats()]),
                ),
            ),
        )

    cr0e4u_module.get_device_info = get_device_info

    # Directly inject our patched device info into the hardware cache
    # This overrides whatever was loaded before our patch ran
    try:
        import deebot_client.hardware as hw_module
        patched_info = get_device_info()
        hw_module._DEVICES["cr0e4u"] = patched_info
        hw_module._NOT_FOUND.discard("cr0e4u")
        _LOGGER.warning(
            "cr0e4u hardware definition patched successfully. "
            "Device type: %s, Map capability: %s",
            patched_info.capabilities.device_type,
            patched_info.capabilities.map is not None,
        )
    except Exception as e:
        _LOGGER.error("Could not inject patched cr0e4u into hardware cache: %s", e)

    _LOGGER.debug("cr0e4u patched for GOAT A3000 LiDAR")


def _patch_clean_info_state() -> None:
    """Patch GetCleanInfo to handle mower-specific idle state correctly."""
    pass  # GetCleanInfo already handles 'idle' state correctly




def log_device_capabilities(device) -> None:
    """Log all capabilities and entities for a device."""
    caps = device.capabilities
    _LOGGER.warning("=== DEVICE DIAGNOSTIC: %s ===", device.device_info.get("nick", "unknown"))
    _LOGGER.warning("Device type: %s", caps.device_type)
    _LOGGER.warning("Device class: %s", device.device_info.get("class"))
    
    # Log all capabilities
    for attr in dir(caps):
        if attr.startswith("_"):
            continue
        val = getattr(caps, attr, None)
        if val is not None:
            _LOGGER.warning("  capability.%s = %s", attr, type(val).__name__)
    
    # Log map specifically
    if caps.map:
        _LOGGER.warning("Map capabilities:")
        for attr in dir(caps.map):
            if attr.startswith("_"):
                continue
            val = getattr(caps.map, attr, None)
            if val is not None:
                _LOGGER.warning("  map.%s = %s", attr, type(val).__name__)
    
    # Log device.map object
    _LOGGER.warning("device.map object: %s", device.map)
    _LOGGER.warning("=== END DIAGNOSTIC ===")


def _patch_get_map_set_p2p() -> None:
    """Add MQTT p2p support to GetMapSet.

    The GOAT A3000 sends getMapSet responses over MQTT p2p channel.
    Without this patch, the library silently drops them with:
    "Command getMapSet does not support p2p handling (yet)"
    """
    from types import MappingProxyType
    from deebot_client.command import CommandMqttP2P, InitParam
    from deebot_client.commands.json.common import JsonCommandMqttP2P
    from deebot_client.commands.json.map import GetMapSet
    from deebot_client.event_bus import EventBus
    from typing import Any

    # Only patch if not already patched
    if issubclass(GetMapSet, CommandMqttP2P):
        _LOGGER.debug("GetMapSet already has p2p support")
        return

    # Add p2p mixin and required attributes
    GetMapSet.__bases__ = GetMapSet.__bases__ + (JsonCommandMqttP2P,)
    GetMapSet._mqtt_params = MappingProxyType({
        "mid": InitParam(str, "mid"),
        "type": InitParam(str, "type"),
    })

    def _handle_mqtt_p2p(self, event_bus: EventBus, response: dict[str, Any]) -> None:
        """Handle response received over the mqtt channel p2p."""
        self.handle(event_bus, response)

    GetMapSet._handle_mqtt_p2p = _handle_mqtt_p2p

    # Re-register in COMMANDS_WITH_MQTT_P2P_HANDLING
    from deebot_client.commands import COMMANDS_WITH_MQTT_P2P_HANDLING
    from deebot_client.const import DataType
    COMMANDS_WITH_MQTT_P2P_HANDLING[DataType.JSON]["getMapSet"] = GetMapSet

    _LOGGER.warning(
        "GetMapSet patched with MQTT p2p support - map data will now flow through"
    )


def _patch_on_mi_handler() -> None:
    """Register OnMI message handler for GOAT mower zone polygon map data.

    The GOAT A3000 sends zone polygon data via chunked onMI MQTT messages.
    Without this patch, the map never renders because the polygon data is
    silently ignored.
    """
    import base64
    import lzma
    import struct
    from collections import defaultdict
    from typing import Any
    from deebot_client.events.map import MapSetEvent, MapSetType, MapSubsetEvent
    from deebot_client.message import HandlingResult, HandlingState, MessageBodyDataDict
    import deebot_client.messages.json as messages_module
    import orjson

    # Check if already registered
    if "onMI" in messages_module.MESSAGES:
        _LOGGER.debug("OnMI handler already registered")
        return

    _chunk_buffer: dict[str, dict[int, bytes]] = defaultdict(dict)
    _chunk_counts: dict[str, int] = {}

    def _decompress_lzma_b64(b64_data: str) -> bytes:
        data = base64.b64decode(b64_data)
        lzma_header = data[0:5]
        len_value = struct.unpack("<I", data[5:9])[0]
        filter_props = lzma._decode_filter_properties(lzma.FILTER_LZMA1, lzma_header)
        dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, None, [filter_props])
        return dec.decompress(data[9:], len_value)

    class OnMI(MessageBodyDataDict):
        """Handler for onMI GOAT mower map chunk messages."""
        NAME = "onMI"

        @classmethod
        def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
            batid = data.get("batid", "")
            serial = int(data.get("serial", 0))
            index = int(data.get("index", 0))
            mid = str(data.get("mid", "1"))
            info = data.get("info", "")
            total_chunks = serial + 1

            if not info or not batid:
                return HandlingResult.analyse()

            try:
                chunk = _decompress_lzma_b64(info)
            except Exception:
                _LOGGER.warning("Failed to decompress onMI chunk %d for batid=%s", index, batid)
                return HandlingResult.analyse()

            _chunk_buffer[batid][index] = chunk
            _chunk_counts[batid] = total_chunks

            _LOGGER.debug("onMI chunk %d/%d (batid=%s, map=%s)", index + 1, total_chunks, batid, mid)

            if len(_chunk_buffer[batid]) < total_chunks:
                return HandlingResult.success()

            try:
                full_bytes = b"".join(_chunk_buffer[batid][i] for i in range(total_chunks))
            except KeyError:
                return HandlingResult.analyse()
            finally:
                del _chunk_buffer[batid]
                _chunk_counts.pop(batid, None)

            try:
                zones = orjson.loads(full_bytes)
            except Exception:
                _LOGGER.warning("Failed to parse onMI JSON for map %s", mid)
                return HandlingResult.analyse()

            _LOGGER.warning("onMI: assembled %d zones for map %s - map should render now!", len(zones), mid)

            subset_ids: list[int] = []
            for zone in zones:
                if not isinstance(zone, list) or len(zone) < 3:
                    continue
                try:
                    zone_id = int(zone[0])
                except (ValueError, TypeError):
                    continue

                parts = zone[2].split(";") if len(zone) > 2 else []
                coord_pairs = [p for p in parts[1:] if "," in p]
                coordinates = ";".join(coord_pairs)

                if not coordinates:
                    continue

                event_bus.notify(MapSubsetEvent(id=zone_id, type=MapSetType.ROOMS, coordinates=coordinates, name=""))
                subset_ids.append(zone_id)

            if subset_ids:
                event_bus.notify(MapSetEvent(MapSetType.ROOMS, subset_ids, mid))

            return HandlingResult.success()

    # Register in the messages dict
    messages_module.MESSAGES["onMI"] = OnMI
    _LOGGER.warning("OnMI handler registered - GOAT mower zone map data will now be processed")
