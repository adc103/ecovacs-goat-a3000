# Ecovacs GOAT A3000 LiDAR - Enhanced Integration

A custom Home Assistant integration that enhances support for the **Ecovacs GOAT A3000 LiDAR** robotic lawn mower (`cr0e4u` device class).

> **Note:** This is a temporary fix while PRs are submitted upstream to [DeebotUniverse/client.py](https://github.com/DeebotUniverse/client.py) and [home-assistant/core](https://github.com/home-assistant/core).

## What This Fixes

The official `deebot-client==18.3.0` library has several issues with the A3000:

| Issue | Status |
|---|---|
| Wrong clean command (`clean_V2` instead of `clean`) | ✅ Fixed |
| Wrong state command (`getCleanInfo_V2` instead of `getCleanInfo`) | ✅ Fixed |
| Incorrect life span (includes `lensBrush` which doesn't exist on A3000) | ✅ Fixed |
| Missing map position tracking | ✅ Added |
| Missing cached map info | ✅ Added |
| Missing map trace | ✅ Added |

## New Services

All services are available under `Developer Tools → Services` in Home Assistant.

### Mowing

| Service | Description | Parameters |
|---|---|---|
| `ecovacs.mow_zone` | Mow a specific zone | `zone_id`: Zone number (1-5) |
| `ecovacs.mow_edge` | Edge/border mow a zone | `zone_id`: Zone number |
| `ecovacs.mow_enhanced` | Enhanced (assart) mow a zone | `zone_id`: Zone number |

### Settings

| Service | Description | Parameters |
|---|---|---|
| `ecovacs.set_rain_delay` | Enable/disable rain delay | `enable`: bool, `delay_minutes`: 0-1440 (default 180) |
| `ecovacs.set_anim_protect` | Set animal protection window | `enable`: bool, `start_time`: "21:0", `end_time`: "6:0" |
| `ecovacs.set_cut_height` | Set blade height | `level`: 1-5 |
| `ecovacs.set_cut_efficiency` | Set mowing efficiency | `level`: 1-3 |
| `ecovacs.set_obstacle_height` | Set obstacle detection sensitivity | `level`: 1-3 |
| `ecovacs.set_video_camera` | Enable/disable camera | `enable`: bool |

### Information (with response)

| Service | Description | Parameters |
|---|---|---|
| `ecovacs.get_zone_parameters` | Get per-zone blade height, cut mode, obstacle settings | None |
| `ecovacs.get_zone_mow_duration` | Get total mow time for a zone (seconds) | `zone_id`: default "0" (all) |

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** → three dots menu → **Custom repositories**
3. Add URL: `https://github.com/adc103/ecovacs-goat-a3000`
4. Category: **Integration**
5. Click **Add**
6. Search for "Ecovacs GOAT A3000" and install
7. Restart Home Assistant

> The existing Ecovacs integration setup is preserved — no need to reconfigure.

## Finding Your Zone IDs

Zone IDs are assigned by the Ecovacs app when you draw your mowing zones. 
To find them, use the Ecovacs app and note which zones you've created — they're numbered starting from 1.
You can also capture them via the `getAreaSet` API call (use Developer Tools → Services to call `ecovacs.raw_get_positions`).

## Known Limitations

- **Video stream**: The A3000 uses AWS Kinesis WebRTC for video — not yet implemented as an HA camera entity
- **Manual joystick control**: Appears to be Bluetooth-only in current firmware
- **Schedule management**: Read-only via `getSchedules` — write support not yet implemented

## Contributing

Traffic was captured from a real GOAT A3000 LiDAR using mitmproxy + Frida on Android.
PRs to upstream repos are in progress:
- [DeebotUniverse/client.py](https://github.com/adc103/client.py/tree/feature/goat-a3000-improvements)
