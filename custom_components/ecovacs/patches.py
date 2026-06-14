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
    _LOGGER.debug("cr0e4u patched for GOAT A3000 LiDAR")


def _patch_clean_info_state() -> None:
    """Patch GetCleanInfo to handle mower-specific idle state correctly."""
    pass  # GetCleanInfo already handles 'idle' state correctly


