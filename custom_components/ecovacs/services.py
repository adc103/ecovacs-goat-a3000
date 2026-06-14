"""Ecovacs services."""

import voluptuous as vol

from homeassistant.components.lawn_mower import DOMAIN as LAWN_MOWER_DOMAIN
from homeassistant.components.vacuum import DOMAIN as VACUUM_DOMAIN
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.helpers import service

from .const import DOMAIN

SERVICE_RAW_GET_POSITIONS = "raw_get_positions"
SERVICE_MOW_ZONE = "mow_zone"
SERVICE_MOW_EDGE = "mow_edge"
SERVICE_MOW_ENHANCED = "mow_enhanced"

SCHEMA_MOW_ZONE = vol.Schema(
    {
        vol.Required("zone_id"): vol.Coerce(str),
    }
)

SCHEMA_MOW_EDGE = vol.Schema(
    {
        vol.Required("zone_id"): vol.Coerce(str),
    }
)

SCHEMA_MOW_ENHANCED = vol.Schema(
    {
        vol.Required("zone_id"): vol.Coerce(str),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    # Vacuum Services
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_RAW_GET_POSITIONS,
        entity_domain=VACUUM_DOMAIN,
        schema=None,
        func="async_raw_get_positions",
        supports_response=SupportsResponse.ONLY,
    )

    # Mower zone services
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_MOW_ZONE,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=SCHEMA_MOW_ZONE,
        func="async_mow_zone",
    )

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_MOW_EDGE,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=SCHEMA_MOW_EDGE,
        func="async_mow_edge",
    )

    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_MOW_ENHANCED,
        entity_domain=LAWN_MOWER_DOMAIN,
        schema=SCHEMA_MOW_ENHANCED,
        func="async_mow_enhanced",
    )
