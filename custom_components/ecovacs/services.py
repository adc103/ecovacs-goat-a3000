"""Ecovacs services."""

import voluptuous as vol

from homeassistant.components.lawn_mower import DOMAIN as LAWN_MOWER_DOMAIN
from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.helpers import service

from .const import DOMAIN

# Vacuum services
SERVICE_RAW_GET_POSITIONS = "raw_get_positions"

# Mower clean services
SERVICE_MOW_ZONE = "mow_zone"
SERVICE_MOW_EDGE = "mow_edge"
SERVICE_MOW_ENHANCED = "mow_enhanced"

# Mower settings services
SERVICE_SET_RAIN_DELAY = "set_rain_delay"
SERVICE_SET_ANIM_PROTECT = "set_anim_protect"
SERVICE_SET_CUT_HEIGHT = "set_cut_height"
SERVICE_SET_CUT_EFFICIENCY = "set_cut_efficiency"
SERVICE_SET_OBSTACLE_HEIGHT = "set_obstacle_height"
SERVICE_SET_VIDEO_CAMERA = "set_video_camera"

# Mower info services
SERVICE_GET_ZONE_PARAMETERS = "get_zone_parameters"
SERVICE_GET_ZONE_MOW_DURATION = "get_zone_mow_duration"


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    # Vacuum services
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_RAW_GET_POSITIONS,
        entity_domain=VACUUM_DOMAIN, schema=None,
        func="async_raw_get_positions",
        supports_response=SupportsResponse.ONLY,
    )

    # Mower clean services
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_MOW_ZONE,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("zone_id"): vol.Coerce(str)}),
        func="async_mow_zone",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_MOW_EDGE,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("zone_id"): vol.Coerce(str)}),
        func="async_mow_edge",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_MOW_ENHANCED,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("zone_id"): vol.Coerce(str)}),
        func="async_mow_enhanced",
    )

    # Mower settings services
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_RAIN_DELAY,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({
            vol.Required("enable"): bool,
            vol.Optional("delay_minutes", default=180): vol.All(int, vol.Range(min=0, max=1440)),
        }),
        func="async_set_rain_delay",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_ANIM_PROTECT,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({
            vol.Required("enable"): bool,
            vol.Optional("start_time", default="21:0"): str,
            vol.Optional("end_time", default="6:0"): str,
        }),
        func="async_set_anim_protect",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_CUT_HEIGHT,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("level"): vol.All(int, vol.Range(min=1, max=5))}),
        func="async_set_cut_height",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_CUT_EFFICIENCY,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("level"): vol.All(int, vol.Range(min=1, max=3))}),
        func="async_set_cut_efficiency",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_OBSTACLE_HEIGHT,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("level"): vol.All(int, vol.Range(min=1, max=3))}),
        func="async_set_obstacle_height",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_SET_VIDEO_CAMERA,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Required("enable"): bool}),
        func="async_set_video_camera",
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_GET_ZONE_PARAMETERS,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=None,
        func="async_get_zone_parameters",
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass, DOMAIN, SERVICE_GET_ZONE_MOW_DURATION,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=vol.Schema({vol.Optional("zone_id", default="0"): vol.Coerce(str)}),
        func="async_get_zone_mow_duration",
        supports_response=SupportsResponse.ONLY,
    )
