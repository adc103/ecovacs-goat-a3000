/**
 * Ecovacs GOAT A3000 LiDAR — Mower Map Card
 *
 * A custom Lovelace card that renders the live mower map with:
 *  - Tappable zone polygons → calls ecovacs.mow_zone service
 *  - Live mower position (auto-refreshes during mowing)
 *  - Current job status overlay
 *  - Start / Pause / Return controls
 *
 * Install via HACS or copy to /config/www/ecovacs-mower-card.js
 * Then add to resources in Lovelace config:
 *   url: /local/ecovacs-mower-card.js
 *   type: module
 *
 * Card config:
 *   type: custom:ecovacs-mower-card
 *   entity: lawn_mower.mower_og        # lawn mower entity
 *   image_entity: image.mower_og_map   # map image entity
 *   camera_entity: camera.mower_og     # optional, for video stream
 *   refresh_interval: 5                # seconds, default 5
 */

const CARD_VERSION = '1.0.0';

// Zone ID → display name mapping (override in card config)
const DEFAULT_ZONE_NAMES = {
  1: 'No-Go Zone',
  2: 'Zone 2',
  3: 'Zone 3',
  4: 'Zone 4',
  5: 'Zone 5',
};

const MOWER_STATES = {
  mowing: { label: 'Mowing', color: '#4aff7b', icon: '🌿' },
  docked: { label: 'Docked', color: '#ffe605', icon: '⚡' },
  paused: { label: 'Paused', color: '#ff9f4a', icon: '⏸' },
  returning: { label: 'Returning', color: '#4a9eff', icon: '🏠' },
  error: { label: 'Error', color: '#ff4444', icon: '⚠️' },
  idle: { label: 'Idle', color: '#aaaaaa', icon: '💤' },
};

class EcovacsMowerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._refreshTimer = null;
    this._svgDoc = null;
    this._zoneElements = new Map(); // zone_id -> SVG element
    this._lastImageUrl = null;
    this._selectedZone = null;
  }

  // ── Card registration ────────────────────────────────────────────────────

  static getConfigElement() {
    return document.createElement('ecovacs-mower-card-editor');
  }

  static getStubConfig() {
    return {
      entity: 'lawn_mower.mower_og',
      image_entity: 'image.mower_og_map',
    };
  }

  getCardSize() {
    return 6;
  }

  // ── Config ───────────────────────────────────────────────────────────────

  setConfig(config) {
    if (!config.entity) throw new Error('ecovacs-mower-card: entity is required');
    if (!config.image_entity) throw new Error('ecovacs-mower-card: image_entity is required');
    this._config = {
      refresh_interval: 5,
      zone_names: DEFAULT_ZONE_NAMES,
      show_obstacles: true,
      show_zone_buttons: true,
      ...config,
      zone_names: { ...DEFAULT_ZONE_NAMES, ...(config.zone_names || {}) },
    };
    this._render();
  }

  // ── HASS updates ─────────────────────────────────────────────────────────

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;

    if (!this.shadowRoot.querySelector('.card')) {
      this._render();
      return;
    }

    // Update status bar on every hass change
    this._updateStatusBar();

    // Refresh map image if state changed or mowing
    const imgState = hass.states[this._config.image_entity];
    const mowerState = hass.states[this._config.entity];
    const isMowing = mowerState?.state === 'mowing';

    const newUrl = imgState ? this._buildImageUrl(imgState) : null;
    if (newUrl && newUrl !== this._lastImageUrl) {
      this._loadSvgMap(newUrl);
      this._lastImageUrl = newUrl;
    }

    // Start/stop auto-refresh timer based on mowing state
    if (isMowing && !this._refreshTimer) {
      this._startRefresh();
    } else if (!isMowing && this._refreshTimer) {
      this._stopRefresh();
    }
  }

  // ── Rendering ────────────────────────────────────────────────────────────

  _render() {
    const shadow = this.shadowRoot;
    shadow.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .card {
          background: var(--ha-card-background, #1c1c1c);
          border-radius: var(--ha-card-border-radius, 12px);
          overflow: hidden;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.3));
        }
        .status-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          background: var(--secondary-background-color, #2a2a2a);
          border-bottom: 1px solid rgba(255,255,255,0.08);
          min-height: 48px;
        }
        .status-left {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .status-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          flex-shrink: 0;
          transition: background 0.3s;
        }
        .status-label {
          font-size: 14px;
          font-weight: 600;
          color: var(--primary-text-color, #fff);
        }
        .status-meta {
          font-size: 12px;
          color: var(--secondary-text-color, #aaa);
        }
        .controls {
          display: flex;
          gap: 6px;
        }
        .btn {
          border: none;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: opacity 0.15s, transform 0.1s;
          display: flex;
          align-items: center;
          gap: 5px;
        }
        .btn:hover { opacity: 0.85; }
        .btn:active { transform: scale(0.96); }
        .btn-start  { background: #4aff7b; color: #1a2a1a; }
        .btn-pause  { background: #ff9f4a; color: #2a1a0a; }
        .btn-dock   { background: #4a9eff; color: #0a1a2a; }
        .btn-stop   { background: #ff4444; color: #fff; }
        .btn:disabled { opacity: 0.35; cursor: default; }

        .map-container {
          position: relative;
          width: 100%;
          background: #c8d8c0;
          min-height: 200px;
          overflow: hidden;
        }
        .map-container img {
          width: 100%;
          height: auto;
          display: block;
          user-select: none;
        }
        .map-loading {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0,0,0,0.4);
          color: #fff;
          font-size: 14px;
          gap: 8px;
        }
        .spinner {
          width: 20px;
          height: 20px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .svg-overlay {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
        }
        .zone-hit-area {
          cursor: pointer;
          fill: transparent;
          stroke: none;
          transition: fill 0.15s;
        }
        .zone-hit-area:hover {
          fill: rgba(255, 255, 255, 0.12);
        }
        .zone-hit-area.selected {
          fill: rgba(255, 255, 255, 0.22);
          stroke: white;
          stroke-width: 3;
        }

        .zone-panel {
          background: var(--secondary-background-color, #2a2a2a);
          border-top: 1px solid rgba(255,255,255,0.08);
          padding: 10px 14px;
        }
        .zone-panel-title {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--secondary-text-color, #888);
          margin-bottom: 8px;
        }
        .zone-buttons {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .zone-btn {
          border: 1px solid rgba(255,255,255,0.15);
          border-radius: 8px;
          padding: 5px 11px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          background: rgba(255,255,255,0.06);
          color: var(--primary-text-color, #fff);
          transition: background 0.15s, border-color 0.15s, transform 0.1s;
          display: flex;
          align-items: center;
          gap: 5px;
        }
        .zone-btn:hover {
          background: rgba(255,255,255,0.14);
          border-color: rgba(255,255,255,0.35);
        }
        .zone-btn:active { transform: scale(0.95); }
        .zone-btn.active {
          background: #4aff7b22;
          border-color: #4aff7b;
          color: #4aff7b;
        }
        .zone-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .toast {
          position: absolute;
          bottom: 60px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(0,0,0,0.82);
          color: #fff;
          padding: 8px 16px;
          border-radius: 20px;
          font-size: 13px;
          pointer-events: none;
          opacity: 0;
          transition: opacity 0.25s;
          white-space: nowrap;
          z-index: 10;
        }
        .toast.show { opacity: 1; }
      </style>

      <ha-card class="card">
        <div class="status-bar">
          <div class="status-left">
            <div class="status-dot" id="statusDot"></div>
            <div>
              <div class="status-label" id="statusLabel">Loading…</div>
              <div class="status-meta" id="statusMeta"></div>
            </div>
          </div>
          <div class="controls">
            <button class="btn btn-start" id="btnStart" title="Start mowing">🌿 Mow</button>
            <button class="btn btn-pause" id="btnPause" title="Pause">⏸</button>
            <button class="btn btn-dock"  id="btnDock"  title="Return to dock">🏠</button>
          </div>
        </div>

        <div class="map-container" id="mapContainer">
          <img id="mapImg" alt="Mower map" />
          <svg class="svg-overlay" id="svgOverlay" xmlns="http://www.w3.org/2000/svg"></svg>
          <div class="map-loading" id="mapLoading">
            <div class="spinner"></div> Loading map…
          </div>
          <div class="toast" id="toast"></div>
        </div>

        <div class="zone-panel" id="zonePanel" style="display:none">
          <div class="zone-panel-title">Tap a zone to mow</div>
          <div class="zone-buttons" id="zoneButtons"></div>
        </div>
      </ha-card>
    `;

    // Button listeners
    this.shadowRoot.getElementById('btnStart').addEventListener('click', () => this._callService('start_mowing'));
    this.shadowRoot.getElementById('btnPause').addEventListener('click', () => this._callService('pause'));
    this.shadowRoot.getElementById('btnDock').addEventListener('click',  () => this._callService('dock'));

    // If hass already set, update
    if (this._hass) {
      this._updateStatusBar();
      const imgState = this._hass.states[this._config.image_entity];
      if (imgState) {
        const url = this._buildImageUrl(imgState);
        this._loadSvgMap(url);
        this._lastImageUrl = url;
      }
    }
  }

  // ── Image loading ────────────────────────────────────────────────────────

  _buildImageUrl(imgState) {
    // Use the state (timestamp) as cache-buster
    const token = imgState.attributes.access_token || '';
    const state = imgState.state || '';
    return `/api/image_proxy/${imgState.entity_id}?token=${token}&state=${encodeURIComponent(state)}`;
  }

  async _loadSvgMap(url) {
    const loading = this.shadowRoot.getElementById('mapLoading');
    const img = this.shadowRoot.getElementById('mapImg');
    const overlay = this.shadowRoot.getElementById('svgOverlay');

    loading.style.display = 'flex';

    try {
      // Fetch the SVG text so we can parse zones
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const svgText = await resp.text();

      // Parse the SVG for zone polygons
      const parser = new DOMParser();
      const svgDoc = parser.parseFromString(svgText, 'image/svg+xml');
      this._svgDoc = svgDoc;

      // Set image as blob URL for display
      const blob = new Blob([svgText], { type: 'image/svg+xml' });
      const blobUrl = URL.createObjectURL(blob);
      img.onload = () => {
        loading.style.display = 'none';
        URL.revokeObjectURL(blobUrl);
        this._buildZoneOverlay(svgDoc, overlay);
      };
      img.src = blobUrl;

    } catch (e) {
      console.error('ecovacs-mower-card: failed to load map', e);
      loading.innerHTML = '⚠️ Map unavailable';
      loading.style.display = 'flex';
    }
  }

  // ── Zone overlay ─────────────────────────────────────────────────────────

  _buildZoneOverlay(svgDoc, overlay) {
    overlay.innerHTML = '';
    this._zoneElements.clear();

    const rootSvg = svgDoc.querySelector('svg');
    if (!rootSvg) return;

    const viewBox = rootSvg.getAttribute('viewBox');
    if (viewBox) overlay.setAttribute('viewBox', viewBox);
    overlay.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    // Extract zone polygons from the SVG
    // Our renderer writes zones with zone labels in adjacent <text> elements
    // Walk all <polygon> elements and find zone-colored ones
    const polygons = svgDoc.querySelectorAll('polygon');
    const texts = Array.from(svgDoc.querySelectorAll('text'));

    // Build zone buttons panel
    const zoneButtons = this.shadowRoot.getElementById('zoneButtons');
    const zonePanel = this.shadowRoot.getElementById('zonePanel');
    zoneButtons.innerHTML = '';
    const foundZones = new Map(); // zone_id -> {polygon, label}

    const ZONE_COLORS = ['#1a6b3a','#1a4a7a','#4a2a7a','#1a6a5a','#6b5a1a'];
    const ZONE_STROKES = ['#2dcc5a','#4a9eff','#8a5eff','#2dccaa','#ccaa2d'];

    polygons.forEach(poly => {
      const fill = poly.getAttribute('fill') || '';
      const colorIdx = ZONE_COLORS.indexOf(fill);
      if (colorIdx === -1) return;

      // Find the text label near this polygon's centroid
      const points = this._parsePolyPoints(poly.getAttribute('points') || '');
      if (points.length < 3) return;
      const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
      const cy = points.reduce((s, p) => s + p[1], 0) / points.length;

      // Find nearest text element
      let zoneId = colorIdx + 2; // fallback: color index → zone ID
      let zoneName = this._config.zone_names[zoneId] || `Zone ${zoneId}`;

      const nearText = texts.find(t => {
        const tx = parseFloat(t.getAttribute('x') || '0');
        const ty = parseFloat(t.getAttribute('y') || '0');
        return Math.abs(tx - cx) < 5000 && Math.abs(ty - cy) < 5000 &&
               t.textContent.startsWith('Zone ');
      });
      if (nearText) {
        const match = nearText.textContent.match(/Zone (\d+)/);
        if (match) {
          zoneId = parseInt(match[1]);
          zoneName = this._config.zone_names[zoneId] || `Zone ${zoneId}`;
        }
      }

      foundZones.set(zoneId, { points, cx, cy, colorIdx });

      // Create hit area in overlay SVG
      const hitPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      hitPoly.setAttribute('points', poly.getAttribute('points'));
      hitPoly.setAttribute('class', 'zone-hit-area');
      hitPoly.setAttribute('data-zone-id', zoneId);
      hitPoly.addEventListener('click', () => this._onZoneTap(zoneId, zoneName));
      hitPoly.addEventListener('mouseenter', () => this._showToast(`Tap to mow ${zoneName}`));
      hitPoly.addEventListener('mouseleave', () => this._hideToast());
      overlay.appendChild(hitPoly);
      this._zoneElements.set(zoneId, hitPoly);
    });

    // Build zone button strip
    if (foundZones.size > 0) {
      const sortedZones = Array.from(foundZones.entries()).sort(([a], [b]) => a - b);
      sortedZones.forEach(([zoneId, {colorIdx}]) => {
        const zoneName = this._config.zone_names[zoneId] || `Zone ${zoneId}`;
        const color = ZONE_STROKES[colorIdx % ZONE_STROKES.length];
        const btn = document.createElement('button');
        btn.className = 'zone-btn';
        btn.setAttribute('data-zone-id', zoneId);
        btn.innerHTML = `<span class="zone-dot" style="background:${color}"></span>${zoneName}`;
        btn.addEventListener('click', () => this._onZoneTap(zoneId, zoneName));
        zoneButtons.appendChild(btn);
      });
      zonePanel.style.display = 'block';
    }
  }

  _parsePolyPoints(pointsStr) {
    return pointsStr.trim().split(/\s+/).map(p => {
      const [x, y] = p.split(',').map(Number);
      return [x, y];
    }).filter(([x, y]) => !isNaN(x) && !isNaN(y));
  }

  // ── Zone tap ─────────────────────────────────────────────────────────────

  _onZoneTap(zoneId, zoneName) {
    const mowerState = this._hass?.states[this._config.entity]?.state;

    // Deselect if already selected
    if (this._selectedZone === zoneId) {
      this._clearZoneSelection();
      return;
    }

    // Clear previous selection
    this._clearZoneSelection();
    this._selectedZone = zoneId;

    // Highlight zone in overlay
    const hitEl = this._zoneElements.get(zoneId);
    if (hitEl) hitEl.classList.add('selected');

    // Highlight zone button
    this.shadowRoot.querySelectorAll('.zone-btn').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.zoneId) === zoneId);
    });

    // If mower is idle/docked, confirm and start mowing
    if (mowerState === 'docked' || mowerState === 'idle') {
      this._showToast(`Starting ${zoneName}…`);
      this._callZoneMow(zoneId, zoneName);
    } else if (mowerState === 'mowing') {
      // Already mowing — show confirmation toast
      this._showToast(`Tap again to switch to ${zoneName}`, 3000);
    } else {
      this._showToast(`${zoneName} selected`, 2000);
    }
  }

  _clearZoneSelection() {
    this._selectedZone = null;
    this._zoneElements.forEach(el => el.classList.remove('selected'));
    this.shadowRoot.querySelectorAll('.zone-btn').forEach(btn => btn.classList.remove('active'));
  }

  _callZoneMow(zoneId, zoneName) {
    if (!this._hass) return;
    this._hass.callService('ecovacs', 'mow_zone', {
      entity_id: this._config.entity,
      zone_id: zoneId,
    }).then(() => {
      this._showToast(`✅ Mowing ${zoneName}`);
    }).catch(err => {
      console.error('ecovacs-mower-card: mow_zone failed', err);
      this._showToast(`⚠️ Failed to start mow`);
    });
  }

  // ── Controls ─────────────────────────────────────────────────────────────

  _callService(action) {
    if (!this._hass) return;
    const domain = 'lawn_mower';
    this._hass.callService(domain, action, {
      entity_id: this._config.entity,
    }).catch(err => {
      console.error(`ecovacs-mower-card: ${action} failed`, err);
      this._showToast(`⚠️ Command failed`);
    });
  }

  // ── Status bar ───────────────────────────────────────────────────────────

  _updateStatusBar() {
    if (!this._hass) return;

    const mowerState = this._hass.states[this._config.entity];
    if (!mowerState) return;

    const state = mowerState.state;
    const attrs = mowerState.attributes;
    const info = MOWER_STATES[state] || MOWER_STATES.idle;

    const dot = this.shadowRoot.getElementById('statusDot');
    const label = this.shadowRoot.getElementById('statusLabel');
    const meta = this.shadowRoot.getElementById('statusMeta');
    const btnStart = this.shadowRoot.getElementById('btnStart');
    const btnPause = this.shadowRoot.getElementById('btnPause');
    const btnDock  = this.shadowRoot.getElementById('btnDock');

    dot.style.background = info.color;
    label.textContent = `${info.icon} ${info.label}`;

    // Meta line: battery + area if available
    const parts = [];
    if (attrs.battery_level != null) parts.push(`🔋 ${attrs.battery_level}%`);
    if (attrs.mowed_area)            parts.push(`📐 ${attrs.mowed_area} m²`);
    meta.textContent = parts.join('  ·  ');

    // Button states
    btnStart.disabled = state === 'mowing';
    btnPause.disabled = state !== 'mowing';
    btnDock.disabled  = state === 'docked';
  }

  // ── Auto-refresh ─────────────────────────────────────────────────────────

  _startRefresh() {
    if (this._refreshTimer) return;
    const interval = (this._config.refresh_interval || 5) * 1000;
    this._refreshTimer = setInterval(() => {
      const imgState = this._hass?.states[this._config.image_entity];
      if (imgState) {
        const url = this._buildImageUrl(imgState);
        this._loadSvgMap(url);
        this._lastImageUrl = url;
      }
    }, interval);
  }

  _stopRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  // ── Toast ────────────────────────────────────────────────────────────────

  _showToast(msg, duration = 2000) {
    const toast = this.shadowRoot.getElementById('toast');
    if (!toast) return;
    if (this._toastTimer) clearTimeout(this._toastTimer);
    toast.textContent = msg;
    toast.classList.add('show');
    this._toastTimer = setTimeout(() => toast.classList.remove('show'), duration);
  }

  _hideToast() {
    const toast = this.shadowRoot.getElementById('toast');
    if (toast) toast.classList.remove('show');
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────

  disconnectedCallback() {
    this._stopRefresh();
  }
}

// ── Card editor (basic) ──────────────────────────────────────────────────────

class EcovacsMowerCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  get config() { return this._config; }
}

// ── Registration ─────────────────────────────────────────────────────────────

customElements.define('ecovacs-mower-card', EcovacsMowerCard);
customElements.define('ecovacs-mower-card-editor', EcovacsMowerCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ecovacs-mower-card',
  name: 'Ecovacs Mower Map',
  description: 'Interactive map card for the GOAT A3000 LiDAR robot lawn mower',
  preview: true,
  documentationURL: 'https://github.com/adc103/ecovacs-goat-a3000',
});

console.info(
  `%c ECOVACS-MOWER-CARD %c v${CARD_VERSION} `,
  'background:#4aff7b;color:#1a2a1a;font-weight:bold;padding:2px 6px;border-radius:3px 0 0 3px',
  'background:#1a2a1a;color:#4aff7b;font-weight:bold;padding:2px 6px;border-radius:0 3px 3px 0',
);
