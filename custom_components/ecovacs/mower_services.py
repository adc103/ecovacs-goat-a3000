"""Additional services for Ecovacs GOAT A3000 LiDAR mower.

Implements commands discovered via traffic analysis:
- Rain delay control
- Animal protection window
- Cut height
- Cut efficiency  
- Obstacle height
- Per-zone parameters
- Zone mow duration
- Video camera toggle
- Schedule state
- Manual control state
"""
from __future__ import annotations

import logging
from typing import Any

from deebot_client.command import Command
from deebot_client.commands.json.common import ExecuteCommand, JsonCommandWithMessageHandling
from deebot_client.message import HandlingResult, MessageBodyDataDict

_LOGGER = logging.getLogger(__name__)


class SetRainDelay(ExecuteCommand):
    """Set rain delay command."""
    NAME = "setRainDelay"

    def __init__(self, enable: bool, delay: int = 180) -> None:
        super().__init__({"enable": 1 if enable else 0, "delay": delay})


class GetRainDelay(JsonCommandWithMessageHandling, MessageBodyDataDict):
    """Get rain delay command."""
    NAME = "getRainDelay"

    @classmethod
    def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
        from homeassistant.core import HomeAssistant
        event_bus.notify_raw("rain_delay", data)
        return HandlingResult.success()


class SetAnimProtect(ExecuteCommand):
    """Set animal protection command."""
    NAME = "setAnimProtect"

    def __init__(self, enable: bool, start: str = "21:0", end: str = "6:0") -> None:
        super().__init__({"enable": 1 if enable else 0, "start": start, "end": end})


class GetAnimProtect(JsonCommandWithMessageHandling, MessageBodyDataDict):
    """Get animal protection command."""
    NAME = "getAnimProtect"

    @classmethod
    def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
        event_bus.notify_raw("anim_protect", data)
        return HandlingResult.success()


class SetCutHeight(ExecuteCommand):
    """Set cut height command."""
    NAME = "setCutHeight"

    def __init__(self, level: int) -> None:
        super().__init__({"level": level})


class SetCutEfficiency(ExecuteCommand):
    """Set cut efficiency command."""
    NAME = "setCutEfficiency"

    def __init__(self, level: int) -> None:
        super().__init__({"level": level})


class SetObstacleHeight(ExecuteCommand):
    """Set obstacle height sensitivity command."""
    NAME = "setObstacleHeight"

    def __init__(self, level: int) -> None:
        super().__init__({"level": level})


class GetAreaParameter(JsonCommandWithMessageHandling, MessageBodyDataDict):
    """Get per-zone area parameters."""
    NAME = "getAreaParameter"

    @classmethod
    def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
        event_bus.notify_raw("area_parameter", data)
        return HandlingResult.success()


class GetAreasMowDuration(JsonCommandWithMessageHandling, MessageBodyDataDict):
    """Get total mow duration for zones."""
    NAME = "getAreasMowDuration"

    def __init__(self, area_ids: str = "0") -> None:
        super().__init__({"mowAreaIds": area_ids})

    @classmethod
    def _handle_body_data_dict(cls, event_bus: Any, data: dict[str, Any]) -> HandlingResult:
        event_bus.notify_raw("areas_mow_duration", data)
        return HandlingResult.success()


class SetVideoCamera(ExecuteCommand):
    """Set video camera on/off."""
    NAME = "setVideoCamera"

    def __init__(self, enable: bool) -> None:
        super().__init__({"camera": 1 if enable else 0})
