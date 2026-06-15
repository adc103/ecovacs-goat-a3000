# Ecovacs GOAT A3000 LiDAR — Home Assistant Integration

A custom Home Assistant integration for the **Ecovacs GOAT A3000 LiDAR** robot lawn mower, including an interactive map card.

## Features

- 🗺️ **Live map** — zones, connector paths, LiDAR-detected obstacles, dock position
- 🟢 **Tappable zones** — tap any zone on the map to start mowing it
- 📍 **Live mower position** — updates in real time while mowing
- ⚡ **Controls** — Start / Pause / Return to dock from the card
- 🌿 **Zone mowing** — mow specific zones via service or map tap
- 🔋 **Sensors** — battery, mowed area, blade lifespan, error state
- 🏃 **Activity history** — mow log with area and duration

## Installation

### HACS (Recommended)

1. In HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/adc103/ecovacs-goat-a3000` as type **Integration**
3. Install **Ecovacs GOAT A3000 LiDAR**
4. Restart Home Assistant
5. Go to Settings → Integrations → Add → **Ecovacs**

### Lovelace Card Resource

After installing, add the card JS as a Lovelace resource:

**Settings → Dashboards → Resources → Add resource:**
```
URL: /local/ecovacs-mower-card.js
Type: JavaScript module
```

Or in `configuration.yaml`:
```yaml
lovelace:
  resources:
    - url: /local/ecovacs-mower-card.js
      type: module
```

## Map Card Usage

```yaml
type: custom:ecovacs-mower-card
entity: lawn_mower.mower_og
image_entity: image.mower_og_map
refresh_interval: 5   # seconds between map refreshes while mowing
zone_names:           # optional custom zone names
  2: Front Lawn
  3: Back Lawn
  4: Side Garden
  5: Passage
```

## Services

| Service | Description |
|---------|-------------|
| `ecovacs.mow_zone` | Mow a specific zone by ID |
| `ecovacs.mow_edge` | Edge/border mowing |
| `ecovacs.mow_enhanced` | Enhanced mowing mode |
| `ecovacs.set_rain_delay` | Set rain delay (hours) |
| `ecovacs.set_cut_height` | Set blade cut height |

## Supported Firmware

Tested with firmware `1.13.31` on the GOAT A3000 LiDAR (`cr0e4u`).
