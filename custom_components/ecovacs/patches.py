"""Patches for GOAT A3000 LiDAR (cr0e4u) support.

This module monkey-patches the deebot_client library to:
1. Fix cr0e4u hardware definition (correct commands, life span, map support)
2. Add CleanMower and CleanMowerArea commands
"""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


def _patch_on_pos_handler() -> None:
    """Register onPos MQTT handler to capture live mower position and heading."""
    from deebot_client.mqtt_client import MqttClient  # noqa: PLC0415

    original_handle = getattr(MqttClient, '_handle_message', None)
    if original_handle is None:
        return

    # Register via the message handler subscription map
    try:
        from deebot_client.event_bus import EventBus  # noqa: PLC0415
        from deebot_client.events import PositionEvent  # noqa: PLC0415

        def _on_pos_event(event: PositionEvent) -> None:
            global _GLOBAL_MOWER_HEADING, _GLOBAL_TRACE_STORE
            try:
                x = getattr(event, 'x', None) or getattr(event, 'deebot_x', None)
                y = getattr(event, 'y', None) or getattr(event, 'deebot_y', None)
                a = getattr(event, 'a', None) or getattr(event, 'angle', 0)
                if x is not None and y is not None:
                    _GLOBAL_MOWER_HEADING = int(a or 0)
                    _GLOBAL_TRACE_STORE.append((int(x), int(y), int(a or 0)))
                    # Cap trace at 10000 points to avoid memory issues
                    if len(_GLOBAL_TRACE_STORE) > 10000:
                        _GLOBAL_TRACE_STORE = _GLOBAL_TRACE_STORE[-10000:]
            except Exception:
                pass

        # Store for use in __init__.py when setting up device
        _POS_EVENT_HANDLER = _on_pos_event
        _LOGGER.debug("onPos event handler prepared")
    except ImportError:
        pass


def _register_pos_handler_for_device(event_bus) -> None:
    """Register position event handler on a device's event bus."""
    global _GLOBAL_MOWER_HEADING, _GLOBAL_TRACE_STORE
    try:
        from deebot_client.events import PositionEvent  # noqa: PLC0415

        def _on_pos(event: PositionEvent) -> None:
            global _GLOBAL_MOWER_HEADING
            try:
                # PositionEvent has deebot_position with x, y, a
                pos = getattr(event, 'deebot_position', None)
                if pos is None:
                    return
                x = getattr(pos, 'x', None)
                y = getattr(pos, 'y', None)
                a = getattr(pos, 'a', 0)
                invalid = getattr(pos, 'invalid', False)
                if x is not None and y is not None and not invalid:
                    _GLOBAL_MOWER_HEADING = int(a or 0)
                    _GLOBAL_TRACE_STORE.append((int(x), int(y), int(a or 0)))
                    if len(_GLOBAL_TRACE_STORE) > 10000:
                        _GLOBAL_TRACE_STORE = _GLOBAL_TRACE_STORE[-10000:]
            except Exception as e:
                _LOGGER.debug("onPos handler error: %s", e)

        event_bus.subscribe(PositionEvent, _on_pos)
        _LOGGER.warning("onPos handler registered — live trace accumulation active")
    except Exception as e:
        _LOGGER.warning("Could not register onPos handler: %s", e)


def _patch_on_clean_info_handler() -> None:
    """Patch to capture onCleanInfo for active zone tracking."""
    pass  # Handled via event subscription in controller setup


def _on_clean_info_for_device(event_bus) -> None:
    """Register CleanInfoEvent handler to track active zone and clear trace on new mow."""
    global _GLOBAL_ACTIVE_ZONE, _GLOBAL_TRACE_STORE
    try:
        from deebot_client.events import CleanInfoEvent  # noqa: PLC0415

        def _on_clean(event: CleanInfoEvent) -> None:
            global _GLOBAL_ACTIVE_ZONE, _GLOBAL_TRACE_STORE
            try:
                # Extract zone being mowed from event
                content = getattr(event, 'content', None)
                if content and getattr(content, 'type', None) == 'spotArea':
                    zone_id = getattr(content, 'value', None)
                    if zone_id != _GLOBAL_ACTIVE_ZONE:
                        # New zone started — clear old trace
                        _LOGGER.warning("New mow zone: %s (was %s) — clearing trace", zone_id, _GLOBAL_ACTIVE_ZONE)
                        _GLOBAL_ACTIVE_ZONE = zone_id
                        _GLOBAL_TRACE_STORE = []
            except Exception as e:
                _LOGGER.debug("onCleanInfo handler error: %s", e)

        event_bus.subscribe(CleanInfoEvent, _on_clean)
        _LOGGER.warning("onCleanInfo handler registered — active zone tracking active")
    except Exception as e:
        _LOGGER.warning("Could not register onCleanInfo handler: %s", e)


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

    class OnMI(MessageBodyDataDict):
        """Handler for onMI GOAT mower map chunk messages.
        
        The LZMA header + uncompressed length is only in chunk 0 (bytes 0-8).
        Chunks 1+ contain raw continuation compressed data with no header.
        All raw compressed bytes must be concatenated before decompressing.
        """
        NAME = "onMI"

        @classmethod
        def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
            batid = data.get("batid", "")
            serial = int(data.get("serial", 0))
            index = int(data.get("index", 0))
            mid = str(data.get("mid", "1"))
            info = data.get("info", "")
            total_chunks = serial  # serial IS the total count, indices run 0 to serial-1

            if not info or not batid:
                return HandlingResult.analyse()

            try:
                raw = base64.b64decode(info)
            except Exception:
                _LOGGER.warning("Failed to base64-decode onMI chunk %d for batid=%s", index, batid)
                return HandlingResult.analyse()

            _chunk_buffer[batid][index] = raw
            _chunk_counts[batid] = total_chunks

            _LOGGER.debug("onMI chunk %d/%d (batid=%s, map=%s)", index + 1, total_chunks, batid, mid)

            if len(_chunk_buffer[batid]) < total_chunks:
                return HandlingResult.success()

            try:
                all_raw = b"".join(_chunk_buffer[batid][i] for i in range(total_chunks))
            except KeyError:
                return HandlingResult.analyse()
            finally:
                del _chunk_buffer[batid]
                _chunk_counts.pop(batid, None)

            # Chunk 0 has the LZMA header (5 bytes) + uncompressed length (4 bytes)
            # Chunks 1+ are raw continuation compressed data
            try:
                lzma_header = all_raw[0:5]
                total_len = struct.unpack("<I", all_raw[5:9])[0]
                compressed = all_raw[9:]
                _LOGGER.warning("onMI: decompressing %d bytes -> expected %d bytes for batid=%s", len(compressed), total_len, batid)
                filter_props = lzma._decode_filter_properties(lzma.FILTER_LZMA1, lzma_header)
                dec = lzma.LZMADecompressor(lzma.FORMAT_RAW, None, [filter_props])
                full_bytes = dec.decompress(compressed, total_len)
                _LOGGER.warning("onMI: decompressed %d bytes for batid=%s", len(full_bytes), batid)
            except Exception as e:
                _LOGGER.warning("onMI: decompression failed for batid=%s: %s", batid, e, exc_info=True)
                return HandlingResult.analyse()

            try:
                zones = orjson.loads(full_bytes)
                _LOGGER.warning("onMI: parsed JSON with %d entries for batid=%s", len(zones), batid)
            except Exception as e:
                _LOGGER.warning("onMI: JSON parse failed for batid=%s: %s", batid, e, exc_info=True)
                return HandlingResult.analyse()

            _LOGGER.warning("onMI: assembled %d entries for map %s (batid=%s)", len(zones), mid, batid)

            from custom_components.ecovacs.patches import (
                update_zone_store,
                _GLOBAL_ZONE_STORE, _GLOBAL_PATH_STORE,
                _GLOBAL_OBSTACLE_STORE, _GLOBAL_DOCK_STORE,
            )
            from custom_components.ecovacs.map_renderer import parse_onmi_entry

            if mid not in _GLOBAL_PATH_STORE:
                _GLOBAL_PATH_STORE[mid] = []
            if mid not in _GLOBAL_OBSTACLE_STORE:
                _GLOBAL_OBSTACLE_STORE[mid] = []

            subset_ids: list[int] = []
            new_zones = 0
            new_paths = 0
            new_obstacles = 0

            for zone in zones:
                parsed = parse_onmi_entry(zone)

                # Zone polygons
                for zone_id, pts in parsed["zone_polygons"].items():
                    coords = ";".join(f"{x},{y}" for x, y in pts)
                    update_zone_store(mid, zone_id, coords)
                    if zone_id not in subset_ids:
                        subset_ids.append(zone_id)
                    new_zones += 1

                # Connector paths
                seen_path_labels = {label for label, _ in _GLOBAL_PATH_STORE[mid]}
                for label, pts in parsed["path_polygons"]:
                    if label not in seen_path_labels:
                        coords = ";".join(f"{x},{y}" for x, y in pts)
                        _GLOBAL_PATH_STORE[mid].append((label, coords))
                        seen_path_labels.add(label)
                        new_paths += 1

                # Obstacles
                seen_obs_ids = {obs_id for obs_id, _ in _GLOBAL_OBSTACLE_STORE[mid]}
                for obs_id, pts in parsed["obstacle_polygons"]:
                    if obs_id not in seen_obs_ids:
                        coords = ";".join(f"{x},{y}" for x, y in pts)
                        _GLOBAL_OBSTACLE_STORE[mid].append((obs_id, coords))
                        seen_obs_ids.add(obs_id)
                        new_obstacles += 1

                # Dock outline
                if parsed["dock_outline"] and mid not in _GLOBAL_DOCK_STORE:
                    _GLOBAL_DOCK_STORE[mid] = parsed["dock_outline"]

            _LOGGER.warning(
                "onMI: stored zones=%s paths=%d obstacles=%d (batid=%s)",
                list(_GLOBAL_ZONE_STORE.get(mid, {}).keys()),
                len(_GLOBAL_PATH_STORE.get(mid, [])),
                len(_GLOBAL_OBSTACLE_STORE.get(mid, [])),
                batid,
            )

            # Fire MapChangedEvent to trigger image entity refresh
            try:
                from datetime import datetime, timezone
                from deebot_client.events.map import MapChangedEvent
                event_bus.notify(MapChangedEvent(datetime.now(timezone.utc)))
                _LOGGER.warning("Fired MapChangedEvent after assembling %d zones", len(subset_ids))
            except Exception as e:
                _LOGGER.warning("Failed to fire MapChangedEvent: %s", e, exc_info=True)

            return HandlingResult.success()

    # Register for both onMI (main zone polygons) and onArI (sub-zone polygons)
    messages_module.MESSAGES["onMI"] = OnMI
    messages_module.MESSAGES["onArI"] = OnMI
    _LOGGER.warning("OnMI/onArI handlers registered - GOAT mower zone map data will now be processed")


async def async_request_map_refresh(device) -> None:
    """Request map data refresh from mower.

    1. Fetches getAreaSet (HTTP) to get all zone centroids as placeholders
    2. Sends GetMapSet (MQTT) to trigger onMI/onArI polygon pushes
    """
    import asyncio
    from deebot_client.commands.json.map import GetMapSet
    from deebot_client.events.map import MapSetType

    # Wait for MQTT connection to stabilize
    await asyncio.sleep(5)

    _LOGGER.warning("Requesting map data refresh from mower")

    # Step 1: fetch zone centroids via getAreaSet HTTP command
    # This gives us all zone IDs even if no polygon data is available
    try:
        from deebot_client.commands.json.common import ExecuteCommand
        import json, base64, lzma, struct

        class GetAreaSet(ExecuteCommand):
            NAME = "getAreaSet"
            def __init__(self, mid="1", aid="0", area_type="ar"):
                super().__init__({"mid": mid, "aid": aid, "type": area_type})

        for area_type in ["ar", "vw", "nc"]:
            result = await device.execute_command(GetAreaSet(area_type=area_type))
            _LOGGER.warning("getAreaSet type=%s result=%s", area_type, str(result)[:200] if result else None)
    except Exception as e:
        _LOGGER.warning("getAreaSet fetch error: %s", e)

    # Step 2: trigger MQTT onMI/onArI pushes via GetMapSet
    try:
        for map_type in [MapSetType.ROOMS, MapSetType.VIRTUAL_WALLS, MapSetType.NO_MOP_ZONES]:
            await device.execute_command(GetMapSet("1", map_type))
            await asyncio.sleep(0.5)
        _LOGGER.warning("Map refresh commands sent - waiting for onMI chunks")
    except Exception as e:
        _LOGGER.warning("Failed to request map refresh: %s", e)


# ── Global map data stores ──────────────────────────────────────────────────
# All stores are keyed by map ID (mid), typically "1"
# Populated by OnMI/onArI MQTT message handlers

_GLOBAL_ZONE_STORE:     dict[str, dict[int, str]]              = {}  # zone_id -> coord str
_GLOBAL_PATH_STORE:     dict[str, list[tuple[str, str]]]       = {}  # [(label, coord_str)]
_GLOBAL_OBSTACLE_STORE: dict[str, list[tuple[int, str]]]       = {}  # [(obs_id, coord_str)]
_GLOBAL_DOCK_STORE:     dict[str, list[tuple[int, int]]]       = {}  # [(x, y)]


def get_zone_store(mid: str = "1") -> dict[int, str]:
    return _GLOBAL_ZONE_STORE.get(mid, {})

def get_path_store(mid: str = "1") -> list[tuple[str, str]]:
    return _GLOBAL_PATH_STORE.get(mid, [])

def get_obstacle_store(mid: str = "1") -> list[tuple[int, str]]:
    return _GLOBAL_OBSTACLE_STORE.get(mid, [])

def get_dock_store(mid: str = "1") -> list[tuple[int, int]]:
    return _GLOBAL_DOCK_STORE.get(mid, [])


# ── Live mow trace store ─────────────────────────────────────────────────────
# Accumulates onPos positions during active mow, cleared on new mow start
# Format: [(x, y, heading_degrees)]
_GLOBAL_TRACE_STORE: list[tuple[int, int, int]] = []
_GLOBAL_MOWER_HEADING: int = 0
_GLOBAL_ACTIVE_ZONE: str | None = None


def get_trace_store() -> list[tuple[int, int, int]]:
    return _GLOBAL_TRACE_STORE

def get_mower_heading() -> int:
    return _GLOBAL_MOWER_HEADING

def get_active_zone() -> str | None:
    return _GLOBAL_ACTIVE_ZONE

def clear_trace_store() -> None:
    global _GLOBAL_TRACE_STORE
    _GLOBAL_TRACE_STORE = []

def update_zone_store(mid: str, zone_id: int, coordinates: str) -> None:
    if mid not in _GLOBAL_ZONE_STORE:
        _GLOBAL_ZONE_STORE[mid] = {}
    existing = _GLOBAL_ZONE_STORE[mid].get(zone_id, "")
    if len(coordinates.split(";")) > len(existing.split(";")):
        _GLOBAL_ZONE_STORE[mid][zone_id] = coordinates
