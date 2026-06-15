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

    Copies the card JS to /config/www/ (served as /local/) and registers
    it as a Lovelace resource. /local/ is HA's standard user-file web path
    and is always available — no HTTP path hacks needed.
    """
    import pathlib
    import shutil

    src = pathlib.Path(__file__).parent / _CARD_FILENAME
    if not src.exists():
        _LOGGER_INIT.warning("ecovacs-mower-card.js not found — map card unavailable")
        return

    # Copy to /config/www/ so HA serves it as /local/ecovacs-mower-card.js
    www_dir = pathlib.Path(hass.config.config_dir) / "www"
    dst = www_dir / _CARD_FILENAME

    try:
        www_dir.mkdir(exist_ok=True)
        # Only copy if source is newer or destination missing
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            await hass.async_add_executor_job(shutil.copy2, str(src), str(dst))
            _LOGGER_INIT.debug("Copied %s to %s", _CARD_FILENAME, dst)
    except Exception as err:
        _LOGGER_INIT.warning("Could not copy card JS to www/: %s", err)
        return

    # Register as a Lovelace resource if not already present
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection  # noqa: PLC0415
        lovelace = hass.data.get("lovelace")
        resources: ResourceStorageCollection | None = getattr(lovelace, "resources", None)
        if resources is not None:
            await resources.async_load()
            urls = [r.get("url", "") for r in resources.async_items()]
            if any("ecovacs-mower-card" in u for u in urls):
                _LOGGER_INIT.debug("Lovelace resource already registered")
                return
            await resources.async_create_item({"res_type": "module", "url": _CARD_URL})
            _LOGGER_INIT.warning(
                "Ecovacs mower card registered (%s) — hard-refresh your browser (Ctrl+Shift+R)",
                _CARD_URL,
            )
            return
    except Exception as err:
        _LOGGER_INIT.debug("Auto Lovelace registration failed: %s", err)

    # Fallback: persistent notification with manual instructions
    from homeassistant.components.persistent_notification import async_create  # noqa: PLC0415
    async_create(
        hass,
        title="Ecovacs Mower Card — one-time setup required",
        message=(
            "The interactive mower map card needs to be added as a Lovelace resource:\n\n"
            "1. Go to **Settings → Dashboards → ⋮ → Resources**\n"
            "2. **+ Add Resource**\n"
            "3. URL: `{url}`  ·  Type: **JavaScript module**\n"
            "4. Click Create then **hard-refresh** your browser (Ctrl+Shift+R)\n\n"
            "This is a one-time step."
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
