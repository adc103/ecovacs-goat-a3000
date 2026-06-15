"""Support for Ecovacs Deebot vacuums."""

from sucks import VacBot

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .patches import apply_patches

# Apply patches for GOAT A3000 LiDAR improvements
import json as _json, pathlib as _pathlib
try:
    _manifest = _json.loads((_pathlib.Path(__file__).parent / "manifest.json").read_text())
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "=== Ecovacs GOAT A3000 Enhanced v%s loading ===",
        _manifest.get("version", "unknown")
    )
except Exception:
    pass
apply_patches()
from .controller import EcovacsController
from .services import async_setup_services

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]
type EcovacsConfigEntry = ConfigEntry[EcovacsController]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


LOVELACE_CARD_URL = "/hacsfiles/ecovacs-goat-a3000/ecovacs-mower-card.js"
LOVELACE_CARD_URL_FALLBACK = "/local/ecovacs-mower-card.js"
_LOGGER_INIT = logging.getLogger(__name__)


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register the mower map card as a Lovelace resource if not already present.

    Uses HA's frontend module registration so the card JS is served directly
    from the custom_components directory — no manual resource steps needed.
    """
    import pathlib

    card_file = pathlib.Path(__file__).parent / "ecovacs-mower-card.js"
    if not card_file.exists():
        _LOGGER_INIT.warning("ecovacs-mower-card.js not found at %s", card_file)
        return

    card_url = f"/ecovacs_mower_card/ecovacs-mower-card.js"

    # Serve the JS file via HA's HTTP server
    try:
        hass.http.register_static_path(
            "/ecovacs_mower_card",
            str(card_file.parent),
            cache_headers=False,
        )
    except Exception as err:
        _LOGGER_INIT.debug("Static path already registered or unavailable: %s", err)

    # Register as a Lovelace resource
    try:
        from homeassistant.components.lovelace import _async_register_resource  # noqa: PLC0415
        await _async_register_resource(hass, card_url, "module")
        _LOGGER_INIT.warning(
            "Registered Lovelace card resource: %s — refresh your browser", card_url
        )
        return
    except (ImportError, Exception):
        pass

    # Fallback: use lovelace storage collection directly
    try:
        lovelace = hass.data.get("lovelace")
        if not lovelace:
            return
        resources = lovelace.get("resources")
        if not resources:
            return

        await resources.async_load()
        existing_urls = [r.get("url", "") for r in resources.async_items()]
        if any("ecovacs-mower-card" in u for u in existing_urls):
            return

        await resources.async_create_item({"res_type": "module", "url": card_url})
        _LOGGER_INIT.warning(
            "Registered Lovelace card resource: %s — refresh your browser", card_url
        )
    except Exception as err:
        _LOGGER_INIT.warning(
            "Could not auto-register Lovelace resource: %s. "
            "Add manually: URL=%s Type=module", err, card_url
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    async_setup_services(hass)
    hass.async_create_task(_async_register_lovelace_resource(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Set up this integration using UI."""
    controller = EcovacsController(hass, entry.data)

    entry.async_on_unload(controller.teardown)

    await controller.initialize()

    entry.runtime_data = controller

    async def _async_wait_connect(device: VacBot) -> None:
        await hass.async_add_executor_job(device.connect_and_wait_until_ready)

    for device in controller.legacy_devices:
        entry.async_create_background_task(
            hass=hass,
            target=_async_wait_connect(device),
            name=f"{entry.title}_wait_connect_{device.vacuum['did']}",
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
