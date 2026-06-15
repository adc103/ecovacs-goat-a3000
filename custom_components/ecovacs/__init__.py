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
_CARD_FILENAME = "ecovacs-mower-card.js"
_CARD_URL = f"/local/{_CARD_FILENAME}"
_NOTIFICATION_ID = "ecovacs_mower_card_resource"


async def _async_setup_lovelace_card(hass: HomeAssistant) -> None:
    """Set up the mower map Lovelace card.

    Copies the card JS to /config/www/ on every startup (always overwrites),
    then updates the Lovelace resource URL to match the current version.
    The versioned URL forces the browser to fetch fresh JS on every update.
    """
    import pathlib
    import shutil
    import json as _json

    src = pathlib.Path(__file__).parent / _CARD_FILENAME
    if not src.exists():
        _LOGGER_INIT.warning("ecovacs-mower-card.js not found — map card unavailable")
        return

    # Get current version for cache-busting URL
    try:
        _manifest = _json.loads(
            (pathlib.Path(__file__).parent / "manifest.json").read_text()
        )
        version = _manifest.get("version", "1").replace(".", "_")
    except Exception:
        version = "1"
    card_url = f"/local/{_CARD_FILENAME}?v={version}"

    # Always copy JS to /config/www/ — overwrite every time so it's always current
    www_dir = pathlib.Path(hass.config.config_dir) / "www"
    dst = www_dir / _CARD_FILENAME
    try:
        www_dir.mkdir(exist_ok=True)
        await hass.async_add_executor_job(shutil.copy2, str(src), str(dst))
        _LOGGER_INIT.warning("ecovacs-mower-card.js copied to %s (v%s)", dst, version.replace("_", "."))
    except Exception as err:
        _LOGGER_INIT.warning("Could not copy card JS: %s", err)
        return

    # Update Lovelace resources — remove ALL old ecovacs-mower-card entries,
    # then register the current versioned URL fresh
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection  # noqa: PLC0415
        lovelace = hass.data.get("lovelace")
        resources: ResourceStorageCollection | None = getattr(lovelace, "resources", None)
        if resources is not None:
            await resources.async_load()
            items = list(resources.async_items())

            # Remove every existing ecovacs-mower-card entry (stale URLs)
            for item in items:
                if "ecovacs-mower-card" in item.get("url", ""):
                    try:
                        await resources.async_delete_item(item["id"])
                        _LOGGER_INIT.warning("Removed old resource entry: %s", item["url"])
                    except Exception as del_err:
                        _LOGGER_INIT.debug("Could not remove resource: %s", del_err)

            # Register fresh versioned URL
            await resources.async_create_item({"res_type": "module", "url": card_url})
            _LOGGER_INIT.warning(
                "Lovelace resource registered: %s — hard-refresh browser!", card_url
            )
            return
    except Exception as err:
        _LOGGER_INIT.warning("Auto Lovelace registration failed: %s", err)

    # Fallback — log and notify
    _LOGGER_INIT.warning(
        "Manual step needed: Settings → Dashboards → ⋮ → Resources → "
        "+ Add Resource → URL: %s, Type: JavaScript module", card_url
    )
    try:
        from homeassistant.components.persistent_notification import async_create  # noqa: PLC0415
        async_create(
            hass,
            title="Ecovacs Mower Card — Action Required",
            message=(
                "Add the mower map card as a Lovelace resource:\n\n"
                "**Settings → Dashboards → ⋮ → Resources → + Add Resource**\n\n"
                f"URL: `{card_url}`\n"
                "Type: **JavaScript module**\n\n"
                "Then hard-refresh your browser (Ctrl+Shift+R)."
            ),
            notification_id=_NOTIFICATION_ID,
        )
    except Exception as err:
        _LOGGER_INIT.warning("Could not create notification: %s", err)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the component."""
    async_setup_services(hass)
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

    # Register live position and clean info handlers for trace/heading
    try:
        from custom_components.ecovacs.patches import (  # noqa: PLC0415
            _register_pos_handler_for_device,
            _on_clean_info_for_device,
        )
        # Controller is stored as entry.runtime_data
        ctrl = entry.runtime_data
        for device in getattr(ctrl, 'devices', []):
            _register_pos_handler_for_device(device.events)
            _on_clean_info_for_device(device.events)
            _LOGGER_INIT.warning("Registered pos/clean handlers for device: %s", getattr(device, 'device_id', '?'))
    except Exception as err:
        _LOGGER_INIT.warning("Could not register pos/clean handlers: %s", err)

    # Set up Lovelace card after all platforms are ready
    # Run only once (first config entry) to avoid duplicate registration
    if not hass.data.get("ecovacs_card_setup_done"):
        hass.data["ecovacs_card_setup_done"] = True
        hass.async_create_task(_async_setup_lovelace_card(hass))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcovacsConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
