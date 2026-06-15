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


_LOGGER_INIT = logging.getLogger(__name__)
_CARD_URL = "/ecovacs_mower_card/ecovacs-mower-card.js"
_NOTIFICATION_ID = "ecovacs_mower_card_resource"


async def _async_setup_lovelace_card(hass: HomeAssistant) -> None:
    """Serve the mower map card JS and register it as a Lovelace resource.

    Serves the file from the integration directory via HA's HTTP server,
    then attempts to auto-register it as a Lovelace module resource.
    If auto-registration fails (HA API varies by version), fires a
    persistent notification with the one-time manual step.
    """
    import pathlib

    card_file = pathlib.Path(__file__).parent / "ecovacs-mower-card.js"
    if not card_file.exists():
        _LOGGER_INIT.warning("ecovacs-mower-card.js not found — map card unavailable")
        return

    # Serve the JS via HA's HTTP server (idempotent — safe to call on every restart)
    try:
        hass.http.register_static_path(
            "/ecovacs_mower_card",
            str(card_file.parent),
            cache_headers=False,
        )
    except Exception:
        pass  # Already registered

    # Check if already in Lovelace resources
    already_registered = False
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection  # noqa: PLC0415
        lovelace = hass.data.get("lovelace")
        resources: ResourceStorageCollection | None = getattr(lovelace, "resources", None)
        if resources is not None:
            await resources.async_load()
            urls = [r.get("url", "") for r in resources.async_items()]
            already_registered = any("ecovacs-mower-card" in u for u in urls)
            if not already_registered:
                await resources.async_create_item(
                    {"res_type": "module", "url": _CARD_URL}
                )
                already_registered = True
                _LOGGER_INIT.warning(
                    "Ecovacs mower card registered automatically (%s). "
                    "Hard-refresh your browser (Ctrl+Shift+R).", _CARD_URL
                )
    except Exception as err:
        _LOGGER_INIT.debug("Auto-register via ResourceStorageCollection failed: %s", err)

    if already_registered:
        return

    # Could not auto-register — fire a one-time persistent notification
    # so the user sees exactly what to do (dismiss once done)
    from homeassistant.components.persistent_notification import async_create  # noqa: PLC0415
    async_create(
        hass,
        title="Ecovacs Mower Card — one-time setup",
        message=(
            "To use the interactive mower map card, add it as a Lovelace resource:\n\n"
            "1. Go to **Settings → Dashboards → ⋮ → Resources**\n"
            "2. Click **+ Add Resource**\n"
            "3. URL: `{url}`\n"
            "4. Type: **JavaScript module**\n"
            "5. Click Create, then **hard-refresh** your browser (Ctrl+Shift+R)\n\n"
            "This only needs to be done once."
        ).format(url=_CARD_URL),
        notification_id=_NOTIFICATION_ID,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    async_setup_services(hass)
    hass.async_create_task(_async_setup_lovelace_card(hass))
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
