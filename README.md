# Ecovacs GOAT A3000 LiDAR — Home Assistant Integration

A custom Home Assistant integration for the **Ecovacs GOAT A3000 LiDAR** robot lawn mower (`cr0e4u`). Built by reverse-engineering the Ecovacs MQTT protocol and extending the upstream `deebot_client` library, which has no mower support.

---

## Features

### 🗺️ Live Map
- Full SVG map rendered from LiDAR data — zones, connector paths, obstacles, dock outline
- **Zone polygons** from `onMI`/`onArI` MQTT messages (LZMA-compressed, chunked)
- **Connector paths** between zones rendered as layered road strokes (dark border → grey surface → white dashed centerline)
- **LiDAR obstacles** — 95+ detected objects (trees, rocks, garden features) shown as brown outlines
- **Dock outline** — actual dock footprint from telemetry
- **Zone labels** always rendered above obstacles for clarity
- **No-go zones** shown with orange hatched fill

### 📍 Live Mower Position & Direction
- Real-time mower position from `onPos` MQTT messages (updates every ~0.5s)
- **Directional arrow** on mower icon showing heading direction
- Mower icon hidden when docked (shown at dock position instead)
- Position accumulates into mow trace during active mowing

### 🌿 Mow Progress Trace
- **Mow coverage trace** rendered as filled semi-transparent polygons from `onMapTrace` data
- Trace **persists across HA restarts** — saved to `/config/.storage/ecovacs_mow_trace.json`
- Trace **accumulates across charge-and-resume cycles** within the same mow job
- Trace **clears automatically when mow job ends** (docks and returns to idle)
- Trace clears on new zone mow start

### ⚡ Status & Progress
- **Status bar** showing: state icon, mow mode, battery %, mowed area, total area, progress %, elapsed time
- **Charging-to-resume state** — when mower pauses for low battery and is charging, shows "Charging · 37% → 80%"
- **Mow progress** — `🌿 4m² / 7m² (60%)` live from `onStats` MQTT messages
- **Elapsed time** — `⏱ 4h 0m` accumulated across charge cycles
- Extended mow state exposed as image entity attributes for dashboard use

### 🎮 Interactive Map Card (`custom:ecovacs-mower-card`)
A custom Lovelace card auto-installed by the integration:

**Mow mode flow:**
1. Tap **🌿 Mow** → modal with 4 mode options
2. **Auto** → starts full auto mow immediately
3. **Select Zone / Edge / Enhanced** → opens zone picker overlay
4. Zone picker shows white pill bubbles positioned over each zone's centroid (parsed from SVG)
5. Tap a zone → confirm with **🌿 Mow [Zone Name]** button

**Controls:**
- ⏸ Pause current mow
- 🏠 Return to dock
- Status dot changes color by state (green=mowing, yellow=docked, orange=paused, blue=charging-to-resume)

**Auto-refresh:** map refreshes every 5 seconds while mowing (configurable)

**Card config:**
```yaml
type: custom:ecovacs-mower-card
entity: lawn_mower.mower_og
image_entity: image.mower_og
refresh_interval: 5        # seconds between refreshes while mowing
zone_names:                # optional custom zone names
  2: Front Lawn
  3: Back Lawn
  4: Side Garden
  5: Passage
```

### 🛠️ Services
| Service | Description |
|---------|-------------|
| `ecovacs.mow_zone` | Mow a specific zone by ID (area mow) |
| `ecovacs.mow_edge` | Edge/border mowing on a zone |
| `ecovacs.mow_enhanced` | Enhanced/mulching mow on a zone |
| `ecovacs.set_rain_delay` | Set rain delay (hours) |
| `ecovacs.set_cut_height` | Set blade cut height |

### 📊 Entities
| Entity | Description |
|--------|-------------|
| `lawn_mower.mower_og` | Main mower entity (state, controls) |
| `image.mower_og` | Live map SVG image |
| `sensor.mower_og_battery` | Battery percentage |
| `sensor.mower_og_area` | Mowed area this session (m²) |
| `sensor.mower_og_mow_duration` | Mow duration |
| `sensor.mower_og_blade_lifespan` | Blade lifespan % |
| `sensor.mower_og_error` | Current error state |
| `sensor.mower_og_mow_state` | Extended mow state (motion, zone, progress) |

---

## Installation

### HACS (Recommended)

1. In HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/adc103/ecovacs-goat-a3000` → Type: **Integration**
3. Install **Ecovacs GOAT A3000 LiDAR**
4. Restart Home Assistant
5. Go to **Settings → Integrations → Add → Ecovacs**
6. Enter your Ecovacs account credentials

The Lovelace card JS is automatically copied to `/config/www/` and registered as a Lovelace resource on every startup. After first install, hard-refresh your browser (**Ctrl+Shift+R**).

### Adding the Map Card

After install and browser refresh, add to any dashboard:

1. Edit dashboard → **+ Add Card → Manual**
2. Paste the YAML config above
3. Save

Or look for **Custom: Ecovacs Mower Map** in the card picker.

---

## How It Works

### The Problem
The upstream [DeebotUniverse/client.py](https://github.com/DeebotUniverse/client.py) has zero support for robot lawn mowers. The GOAT A3000 uses a completely different device type (`cr0e4u`), command set, and map protocol compared to the vacuums the library was designed for.

### Approach: Runtime Patching
Rather than forking the upstream library, this integration applies targeted runtime patches to `deebot_client` at import time via `patches.py`. This means upstream library updates don't break the integration.

### Map Data Protocol
The mower pushes map data via two MQTT message types:

**`onMI`** (21 chunks) and **`onArI`** (16 chunks):
- Each batch is LZMA-compressed with a custom header: `[5-byte LZMA props][4-byte uncompressed length][compressed data]`
- Chunks are accumulated by `batid` (batch ID) and decompressed once complete
- Each entry is a JSON array where multiple fields contain different data types:
  - `field[0]` — group/zone ID
  - `field[1]` — dock outline (`s1` prefix) or connector path (compound prefix like `3,1,4`)
  - `field[2..N]` — zone polygons (simple integer prefix = zone ID) or obstacles (prefix 100-199)
- Zone polygons are semicolon-separated `x,y` coordinate pairs in millimetres from dock (0,0)
- Y axis is flipped for SVG rendering (map Y increases up, SVG Y increases down)

**`onMapTrace`** (chunked, same LZMA format):
- Pushes filled polygons showing the area the mower has actually cut
- Accumulated across charge cycles, cleared when mow job ends

**`onPos`** (every ~0.5s):
- Live mower position `{x, y, a}` where `a` is heading in degrees (0=East, 90=North, CCW positive)
- SVG rotation formula: `svg_angle = 90 - a`

**`onCleanInfo`**, **`onChargeState`**, **`onStats`**, **`onBattery`**:
- Intercepted via `MqttClient._handle_atr` patch to extract mow state, charging status, and progress

### Global Data Stores
All map data is stored in module-level globals in `patches.py`, keyed by map ID:

```python
_GLOBAL_ZONE_STORE     # {mid: {zone_id: "x1,y1;x2,y2;..."}}
_GLOBAL_PATH_STORE     # {mid: [(label, "x1,y1;...")]}
_GLOBAL_OBSTACLE_STORE # {mid: [(obs_id, "x1,y1;...")]}
_GLOBAL_DOCK_STORE     # {mid: [(x, y)]}
_GLOBAL_TRACE_STORE_SVG # ["x1,y1;x2,y2;..."] — mow trace polygons
_GLOBAL_MOWER_HEADING  # int — current heading in degrees
_GLOBAL_MOW_STATE      # dict — motion_state, is_charging, battery, area, time
```

These are populated by MQTT message handlers and read by the image entity to render the SVG.

### Map Rendering (`map_renderer.py`)
Pure Python SVG renderer (the upstream Rust map renderer returns `None` for mowers):

**Render order** (back to front):
1. Background (`#c8d8c0` light grey-green)
2. Connector paths — 3-layer road stroke (dark border → light grey → white dashes)
3. Mowing zones — green fills with distinct color per zone
4. No-go zone — orange hatched fill
5. LiDAR obstacles — subtle brown outlines
6. Mow trace — semi-transparent white filled polygons
7. Zone labels — rendered above obstacles
8. Dock outline + yellow dock marker
9. Mower position + directional arrow

### `map_data.map_subsets` Bypass
The upstream `Map` class subscribes to `MapSubsetEvent` but silently ignores `MapSetType.ROOMS` events (they go through a different path for the vacuum room selector). This integration bypasses `map_data.map_subsets` entirely and uses the global stores instead.

### `_cached_image` Fix
The `EcovacsMap` image entity caches its last rendered image. Without intervention, the placeholder SVG would be cached forever. We subscribe to `MapChangedEvent` and set `_cached_image = None` to force a fresh render when new map data arrives.

### Lovelace Card Auto-Registration
On every startup:
1. `ecovacs-mower-card.js` is copied from `custom_components/ecovacs/` to `/config/www/`
2. All existing `ecovacs-mower-card` Lovelace resource entries are removed
3. A new versioned resource `/local/ecovacs-mower-card.js?v=X_Y_Z` is registered
4. The version query string forces browsers to fetch fresh JS on every update

---

## Key Technical Discoveries

| Discovery | Detail |
|-----------|--------|
| LZMA header format | `[5-byte filter props][4-byte uncompressed len][data]` — no standard LZMA magic |
| `serial` field meaning | Total chunk count (0-indexed), NOT max index |
| Multi-field entries | Each `onMI`/`onArI` entry has multiple zone polygons in fields [2..N], not just [2] |
| `map_subsets` filtering | `deebot_client` silently drops `ROOMS` type events — must use global stores |
| `_cached_image` persistence | Must explicitly set to `None` on map update or placeholder is served forever |
| `onArI` vs `onMI` | Two separate MQTT topics, both must be handled; `onArI` contains zones 4 and 5 |
| Zone numbering | Zone 1 = no-go, Zones 2-5 = mowing areas (from `getAreaSet` type=ar) |
| Path polygons | Compound prefix e.g. `3,1,4` = connector corridor between zones |
| Obstacle IDs | Prefix 100-199 = LiDAR-detected obstacles |
| Heading convention | `a`: 0=East, 90=North, CCW positive (math convention), SVG: `90 - a` |
| `onMapTrace` format | Same LZMA/chunk format as `onMI`; entries are filled mow-area polygons |
| `_handle_atr` intercept | Patch point for `onPos`, `onCleanInfo`, `onMapTrace`, `onChargeState`, `onStats` |
| Charge-and-resume | `onCleanInfo` `trigger=lowBattery` distinguishes pause-to-charge from mow-end |

---

## Supported Hardware

Tested with:
- **GOAT A3000 LiDAR** (`cr0e4u`, `GOAT_INT_G2_LIDAR3000_NA`)
- Firmware `1.13.31`

---

## Known Limitations

- **Cloud dependency** — the mower connects outbound to Ecovacs MQTT broker. Occasionally the mower's MQTT client disconnects (WiFi power-save related) and takes time to reconnect. This is a firmware issue, not an integration issue.
- **Map data on restart** — zone polygons must be re-requested after every HA restart (auto-requested with 5s delay). The map will be blank for ~30 seconds after startup.
- **Mow trace resets on restart** — mow trace is now persisted to `/config/.storage/ecovacs_mow_trace.json` and loaded on startup, but only traces from `onMapTrace` messages are persisted (not `onPos` fallback traces).

---

## Upstream PR Candidates

The following patches are candidates for upstream contribution to [DeebotUniverse/client.py](https://github.com/DeebotUniverse/client.py):

- `cr0e4u` device definition (mower type, blade lifespan, map capability)
- `CleanMower` and `CleanMowerArea` commands
- `GetMapSet` P2P MQTT support
- `onMI`/`onArI` chunked LZMA map handler
