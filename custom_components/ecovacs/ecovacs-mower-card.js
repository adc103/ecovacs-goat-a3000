/**
 * Ecovacs GOAT A3000 LiDAR — Mower Map Card
 * Lovelace custom card for Home Assistant
 *
 * Card config:
 *   type: custom:ecovacs-mower-card
 *   entity: lawn_mower.mower_og
 *   image_entity: image.mower_og
 *   refresh_interval: 5
 *   zone_names:
 *     2: Front Lawn
 *     3: Back Lawn
 */

const CARD_VERSION = '2.2.1';

const _MOWER_COLOR = '#00aaff';

const ZONE_COLORS = {
  2: '#2dcc5a',
  3: '#4a9eff',
  4: '#8a5eff',
  5: '#2dccaa',
  6: '#ccaa2d',
};

const MOWER_STATES = {
  mowing:    { label: 'Mowing',    color: '#4aff7b', icon: '🌿' },
  docked:    { label: 'Docked',    color: '#ffe605', icon: '⚡' },
  paused:    { label: 'Paused',    color: '#ff9f4a', icon: '⏸'  },
  returning: { label: 'Returning', color: '#4a9eff', icon: '🏠' },
  error:     { label: 'Error',     color: '#ff4444', icon: '⚠️' },
  idle:      { label: 'Idle',      color: '#aaaaaa', icon: '💤' },
};

class EcovacsMowerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._refreshTimer = null;
    this._mapLoaded = false;
    this._lastImageState = null;
    this._lastSvg = null;
    this._zoneIds = [];       // zone IDs parsed from SVG
    this._zoneCentroids = {}; // zone_id -> {xPct, yPct}
    this._modalMode = null;   // current modal: 'mode' | 'zone'
    this._selectedZone = null;
    this._selectedMode = null;
    this._mowerAngle = 0;
  }

  static getStubConfig() {
    return { entity: 'lawn_mower.mower_og', image_entity: 'image.mower_og' };
  }

  getCardSize() { return 7; }

  setConfig(config) {
    if (!config.entity) throw new Error('ecovacs-mower-card: entity required');
    if (!config.image_entity) throw new Error('ecovacs-mower-card: image_entity required');
    this._config = {
      refresh_interval: 5,
      zone_names: {},
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot.querySelector('.card')) { this._render(); return; }
    this._updateStatusBar();

    // Update mower heading from state attributes if available
    const mowerState = hass.states[this._config.entity];
    if (mowerState?.attributes?.heading != null) {
      this._mowerAngle = mowerState.attributes.heading;
      this._drawMowerOverlay();
    }

    const imgState = hass.states[this._config.image_entity]?.state;
    if (imgState && imgState !== this._lastImageState) {
      this._lastImageState = imgState;
      this._loadMap();
    }
    const mowing = hass.states[this._config.entity]?.state === 'mowing';
    if (mowing && !this._refreshTimer) this._startRefresh();
    else if (!mowing && this._refreshTimer) this._stopRefresh();
  }

  // ── Render shell ─────────────────────────────────────────────────────────

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :host { display: block; font-family: var(--paper-font-body1_-_font-family, sans-serif); }

        .card {
          background: var(--ha-card-background, #1c1c1c);
          border-radius: var(--ha-card-border-radius, 12px);
          overflow: hidden;
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.3));
        }

        /* ── Status bar ── */
        .status-bar {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px;
          background: var(--secondary-background-color, #2a2a2a);
          border-bottom: 1px solid rgba(255,255,255,0.08);
          min-height: 52px;
        }
        .status-left { display: flex; align-items: center; gap: 10px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; transition: background 0.3s; }
        .status-label { font-size: 14px; font-weight: 600; color: var(--primary-text-color, #fff); }
        .status-meta  { font-size: 12px; color: var(--secondary-text-color, #aaa); margin-top: 2px; }

        .controls { display: flex; gap: 6px; }
        .btn {
          border: none; border-radius: 8px; padding: 7px 13px;
          font-size: 13px; font-weight: 600; cursor: pointer;
          transition: opacity 0.15s, transform 0.1s;
          display: flex; align-items: center; gap: 5px;
        }
        .btn:hover { opacity: 0.85; }
        .btn:active { transform: scale(0.96); }
        .btn:disabled { opacity: 0.3; cursor: default; transform: none; }
        .btn-mow    { background: #4aff7b; color: #0a1f0a; }
        .btn-pause  { background: #ff9f4a; color: #2a1a0a; }
        .btn-dock   { background: #4a9eff; color: #0a1a2a; }

        /* ── Map ── */
        .map-wrap {
          position: relative; width: 100%; background: #c8d8c0;
          min-height: 200px; overflow: hidden;
        }
        .map-wrap img { width: 100%; height: auto; display: block; user-select: none; }
        .map-loading {
          position: absolute; inset: 0;
          display: flex; align-items: center; justify-content: center;
          background: rgba(0,0,0,0.35); color: #fff; font-size: 14px; gap: 8px;
        }
        .spinner {
          width: 20px; height: 20px;
          border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
          border-radius: 50%; animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* ── Mode modal (overlays map) ── */
        .modal {
          position: absolute; inset: 0;
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          background: rgba(0,0,0,0.72); gap: 12px; padding: 20px;
          z-index: 20;
        }
        .modal h3 {
          color: #fff; font-size: 15px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;
        }
        .mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; width: 100%; max-width: 320px; }
        .mode-btn {
          border: 2px solid rgba(255,255,255,0.2); border-radius: 12px;
          padding: 14px 10px; background: rgba(255,255,255,0.06);
          color: #fff; font-size: 13px; font-weight: 600;
          cursor: pointer; text-align: center; transition: all 0.15s;
          display: flex; flex-direction: column; align-items: center; gap: 6px;
        }
        .mode-btn:hover { background: rgba(255,255,255,0.14); border-color: rgba(255,255,255,0.5); }
        .mode-btn .mode-icon { font-size: 26px; }
        .modal-cancel {
          border: none; background: transparent; color: rgba(255,255,255,0.5);
          font-size: 13px; cursor: pointer; margin-top: 4px; padding: 4px 12px;
        }
        .modal-cancel:hover { color: #fff; }

        /* ── Zone picker modal ── */
        .zone-modal {
          position: absolute; inset: 0; z-index: 20;
          background: rgba(0,0,0,0.35);
          display: flex; flex-direction: column;
        }
        .zone-modal-header {
          display: flex; align-items: center; justify-content: space-between;
          padding: 10px 14px;
          background: rgba(0,0,0,0.75);
          color: #fff; font-size: 13px; font-weight: 600;
        }
        .zone-modal-header span { opacity: 0.7; font-weight: 400; }
        .zone-modal-cancel { border: none; background: transparent; color: rgba(255,255,255,0.6); cursor: pointer; font-size: 20px; line-height: 1; }
        .zone-modal-cancel:hover { color: #fff; }

        .zone-bubbles-layer {
          position: relative; flex: 1;
        }
        .zone-bubble {
          position: absolute;
          transform: translate(-50%, -50%);
          border-radius: 50px;
          padding: 7px 16px 7px 10px;
          font-size: 13px; font-weight: 600;
          cursor: pointer; white-space: nowrap;
          border: 2px solid rgba(255,255,255,0.9);
          background: rgba(255,255,255,0.92);
          color: #222;
          transition: all 0.15s;
          display: flex; align-items: center; gap: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .zone-bubble:hover { transform: translate(-50%, -50%) scale(1.06); box-shadow: 0 4px 14px rgba(0,0,0,0.4); }
        .zone-bubble.selected {
          border-color: #4aff7b;
          background: #fff;
          box-shadow: 0 0 0 3px #4aff7b, 0 4px 14px rgba(0,0,0,0.4);
          transform: translate(-50%, -50%) scale(1.08);
        }
        .zone-bubble-circle {
          width: 28px; height: 28px; border-radius: 50%;
          border: 2px solid currentColor;
          flex-shrink: 0;
          display: flex; align-items: center; justify-content: center;
        }
        .zone-bubble.selected .zone-bubble-circle {
          background: #4aff7b; border-color: #4aff7b; color: #fff;
        }

        .zone-modal-footer {
          padding: 12px 14px;
          background: rgba(0,0,0,0.7);
          display: flex; gap: 10px; align-items: center;
        }
        .btn-confirm {
          flex: 1; border: none; border-radius: 10px;
          padding: 11px; font-size: 14px; font-weight: 700;
          background: #4aff7b; color: #0a1f0a; cursor: pointer;
          transition: opacity 0.15s;
        }
        .btn-confirm:disabled { opacity: 0.3; cursor: default; }
        .btn-confirm:not(:disabled):hover { opacity: 0.85; }
        .btn-back {
          border: 1px solid rgba(255,255,255,0.2); border-radius: 10px;
          padding: 11px 16px; font-size: 14px; font-weight: 600;
          background: transparent; color: #fff; cursor: pointer;
        }
        .btn-back:hover { background: rgba(255,255,255,0.08); }

        /* ── Mower overlay ── */
        .mower-overlay {
          position: absolute; inset: 0;
          width: 100%; height: 100%;
          pointer-events: none;
        }

        /* ── Toast ── */
        .toast {
          position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
          background: rgba(0,0,0,0.85); color: #fff;
          padding: 8px 18px; border-radius: 20px; font-size: 13px;
          pointer-events: none; opacity: 0; transition: opacity 0.25s;
          white-space: nowrap; z-index: 30;
        }
        .toast.show { opacity: 1; }
      </style>

      <div class="card">
        <div class="status-bar">
          <div class="status-left">
            <div class="status-dot" id="statusDot"></div>
            <div>
              <div class="status-label" id="statusLabel">Loading…</div>
              <div class="status-meta"  id="statusMeta"></div>
            </div>
          </div>
          <div class="controls">
            <button class="btn btn-mow"   id="btnMow"   title="Start mowing">🌿 Mow</button>
            <button class="btn btn-pause" id="btnPause" title="Pause">⏸</button>
            <button class="btn btn-dock"  id="btnDock"  title="Return to dock">🏠</button>
          </div>
        </div>

        <div class="map-wrap" id="mapWrap">
          <img id="mapImg" alt="Mower map" />
          <svg id="mowerOverlay" class="mower-overlay" xmlns="http://www.w3.org/2000/svg"></svg>
          <div class="map-loading" id="mapLoading"><div class="spinner"></div> Loading map…</div>
          <div class="toast" id="toast"></div>
        </div>
      </div>
    `;

    this.shadowRoot.getElementById('btnMow').addEventListener('click',   () => this._openModeModal());
    this.shadowRoot.getElementById('btnPause').addEventListener('click', () => this._callService('lawn_mower', 'pause'));
    this.shadowRoot.getElementById('btnDock').addEventListener('click',  () => this._callService('lawn_mower', 'dock'));

    if (this._hass) {
      this._updateStatusBar();
      setTimeout(() => { if (!this._mapLoaded) this._loadMap(); }, 800);
    }
  }

  // ── Map loading ───────────────────────────────────────────────────────────

  async _loadMap() {
    const loading = this.shadowRoot.getElementById('mapLoading');
    const img     = this.shadowRoot.getElementById('mapImg');
    if (!loading || !img) return;

    const imgState = this._hass?.states[this._config.image_entity];
    if (!imgState) {
      loading.innerHTML = `⚠️ Entity not found: ${this._config.image_entity}`;
      loading.style.display = 'flex';
      return;
    }

    const token = imgState.attributes.access_token;
    if (!token) { loading.innerHTML = '⚠️ No access token'; loading.style.display = 'flex'; return; }

    const url = `/api/image_proxy/${this._config.image_entity}?token=${token}&t=${Date.now()}`;

    // Only show loading spinner on very first load, not on refreshes
    if (!this._mapLoaded) {
      loading.style.display = 'flex';
      loading.innerHTML = '<div class="spinner"></div> Loading map…';
    }

    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const svg = await resp.text();
      if (!svg.includes('<svg')) throw new Error('Not SVG');

      // Parse zone centroids from SVG using DOMParser
      // Each mowing zone has a <text>Zone N</text> at its centroid
      this._zoneIds = [];
      this._zoneCentroids = {};

      const svgParser = new DOMParser();
      const svgDoc = svgParser.parseFromString(svg, 'image/svg+xml');
      const svgEl = svgDoc.querySelector('svg');
      const vbParts = (svgEl?.getAttribute('viewBox') || '0 0 1 1').trim().split(/\s+/).map(Number);
      const vbW = vbParts[2] || 1;
      const vbH = vbParts[3] || 1;

      svgDoc.querySelectorAll('text').forEach(t => {
        const txt = t.textContent.trim();
        // Match only "Zone N" labels (not ⛔ or ⌂)
        if (!/^Zone \d+$/.test(txt)) return;
        const id = parseInt(txt.replace('Zone ', ''));
        // getAttribute returns the raw attribute value — reliable via DOM
        const x = parseFloat(t.getAttribute('x') || '0');
        const y = parseFloat(t.getAttribute('y') || '0');
        if (isNaN(x) || isNaN(y)) return;
        // Only store first occurrence per zone (largest polygon centroid)
        if (this._zoneCentroids[id]) return;
        this._zoneCentroids[id] = {
          xPct: (x / vbW) * 100,
          yPct: (y / vbH) * 100,
        };
        this._zoneIds.push(id);
      });
      this._zoneIds.sort((a, b) => a - b);
      console.log('ecovacs-mower-card: zones found', this._zoneIds, this._zoneCentroids);

      // Store SVG for reuse in zone picker modal
      this._lastSvg = svg;

      const blob = new Blob([svg], { type: 'image/svg+xml' });
      const blobUrl = URL.createObjectURL(blob);
      img.onload = () => {
        // Hide spinner only needed on first load
        if (!this._mapLoaded) loading.style.display = 'none';
        this._mapLoaded = true;
        URL.revokeObjectURL(blobUrl);
        this._drawMowerOverlay();
      };
      img.onerror = () => {
        if (!this._mapLoaded) loading.style.display = 'none';
        URL.revokeObjectURL(blobUrl);
      };
      img.src = blobUrl;
    } catch(e) {
      loading.innerHTML = `⚠️ ${e.message}`;
      console.error('ecovacs-mower-card: map load failed', e);
    }
  }

  // ── Mode modal ────────────────────────────────────────────────────────────

  _openModeModal() {
    const wrap = this.shadowRoot.getElementById('mapWrap');
    const existing = wrap.querySelector('.modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
      <h3>Select Mow Mode</h3>
      <div class="mode-grid">
        <button class="mode-btn" data-mode="auto">
          <span class="mode-icon">🤖</span>Auto
        </button>
        <button class="mode-btn" data-mode="area">
          <span class="mode-icon">📍</span>Select Zone
        </button>
        <button class="mode-btn" data-mode="edge">
          <span class="mode-icon">🔲</span>Edge
        </button>
        <button class="mode-btn" data-mode="enhanced">
          <span class="mode-icon">⚡</span>Enhanced
        </button>
      </div>
      <button class="modal-cancel">Cancel</button>
    `;

    modal.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        modal.remove();
        if (mode === 'auto') {
          this._startMode(mode);
        } else {
          // area, edge, enhanced all need zone selection first
          this._openZoneModal(mode);
        }
      });
    });
    modal.querySelector('.modal-cancel').addEventListener('click', () => modal.remove());
    wrap.appendChild(modal);
  }

  // ── Zone picker modal ─────────────────────────────────────────────────────

  _openZoneModal(mode = 'area') {
    const wrap = this.shadowRoot.getElementById('mapWrap');
    const img  = this.shadowRoot.getElementById('mapImg');
    const existing = wrap.querySelector('.zone-modal');
    if (existing) existing.remove();

    this._selectedZone = null;
    this._selectedMode = mode;

    const modal = document.createElement('div');
    modal.className = 'zone-modal';
    modal.innerHTML = `
      <div class="zone-modal-header">
        <div id="zmTitle">Select a zone <span>then tap Mow to confirm</span></div>
        <button class="zone-modal-cancel" id="zmCancel">✕</button>
      </div>
      <div class="zone-bubbles-layer" id="bubblesLayer"></div>
      <div class="zone-modal-footer">
        <button class="btn-back" id="zmBack">← Back</button>
        <button class="btn-confirm" id="zmConfirm" disabled>🌿 Mow Zone</button>
      </div>
    `;

    const modeLabels = { area: 'Area Mow', edge: 'Edge Mow', enhanced: 'Enhanced Mow' };
    const modeLabel = modeLabels[mode] || 'Mow';
    modal.querySelector('#zmTitle').innerHTML = `Select zone for <strong>${modeLabel}</strong>`;

    modal.querySelector('#zmCancel').addEventListener('click', () => modal.remove());
    modal.querySelector('#zmBack').addEventListener('click', () => { modal.remove(); this._openModeModal(); });
    modal.querySelector('#zmConfirm').addEventListener('click', () => {
      if (this._selectedZone) {
        modal.remove();
        this._startZoneMow(this._selectedZone, this._selectedMode);
      }
    });

    wrap.appendChild(modal);

    // Place bubbles immediately
    this._placeBubbles(modal);
  }

  _placeBubbles(modal) {
    const layer   = modal.querySelector('#bubblesLayer');
    const confirm = modal.querySelector('#zmConfirm');

    if (!this._zoneIds.length) {
      layer.innerHTML = '<div style="color:white;text-align:center;padding:20px">No zones found</div>';
      return;
    }

    this._zoneIds.forEach(zoneId => {
      const name     = this._config.zone_names?.[zoneId] || `Zone ${zoneId}`;
      const color    = ZONE_COLORS[zoneId] || '#aaa';
      const centroid = this._zoneCentroids?.[zoneId];

      // Use actual centroid from SVG text element position
      const xPct = centroid?.xPct ?? 50;
      const yPct = centroid?.yPct ?? 50;

      const bubble = document.createElement('div');
      bubble.className = 'zone-bubble';
      bubble.style.left = `${xPct}%`;
      bubble.style.top  = `${yPct}%`;
      bubble.innerHTML  = `<span class="zone-bubble-circle" style="color:${color}"></span>${name}`;
      bubble.dataset.zoneId = zoneId;

      bubble.addEventListener('click', () => {
        modal.querySelectorAll('.zone-bubble').forEach(b => b.classList.remove('selected'));
        bubble.classList.add('selected');
        this._selectedZone = zoneId;
        confirm.disabled = false;
        confirm.textContent = `🌿 Mow ${name}`;
      });

      layer.appendChild(bubble);
    });
  }

  // ── Mower overlay (position + direction arrow) ──────────────────────────

  _drawMowerOverlay() {
    const overlay = this.shadowRoot.getElementById('mowerOverlay');
    const img     = this.shadowRoot.getElementById('mapImg');
    if (!overlay || !img || !this._lastSvg) return;

    // Parse mower position from stored SVG
    // Our renderer draws mower as: fill="#00aaff" (blue circle)
    const svgParser = new DOMParser();
    const svgDoc    = svgParser.parseFromString(this._lastSvg, 'image/svg+xml');
    const svgEl     = svgDoc.querySelector('svg');
    const vb        = (svgEl?.getAttribute('viewBox') || '0 0 1 1').trim().split(/\s+/).map(Number);
    const vbW = vb[2] || 1;
    const vbH = vb[3] || 1;

    // Find mower circle (blue fill)
    const mowerCircle = [...svgDoc.querySelectorAll('circle')].find(c =>
      c.getAttribute('fill') === '#00aaff' || c.getAttribute('fill') === _MOWER_COLOR
    );

    overlay.innerHTML = '';

    if (!mowerCircle) return;

    const cx = parseFloat(mowerCircle.getAttribute('cx') || '0');
    const cy = parseFloat(mowerCircle.getAttribute('cy') || '0');
    const cr = parseFloat(mowerCircle.getAttribute('r')  || '10');

    // Convert to percentage of viewBox
    const xPct = (cx / vbW) * 100;
    const yPct = (cy / vbH) * 100;

    // Render mower icon as SVG group positioned via foreignObject % coords
    // Use a viewBox-matching coordinate system
    overlay.setAttribute('viewBox', `0 0 ${vbW} ${vbH}`);
    overlay.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    const angle = this._mowerAngle || 0; // degrees, updated from onPos
    const r = cr * 1.1;
    const arrowLen = r * 2.2;

    // Outer glow ring
    overlay.innerHTML = `
      <circle cx="${cx}" cy="${cy}" r="${r * 1.5}"
        fill="none" stroke="#00aaff" stroke-width="${r * 0.3}" stroke-opacity="0.3"/>

      <!-- Mower body -->
      <circle cx="${cx}" cy="${cy}" r="${r}"
        fill="#1a7bd4" stroke="white" stroke-width="${r * 0.25}"/>

      <!-- Direction arrow -->
      <g transform="translate(${cx},${cy}) rotate(${angle})">
        <polygon
          points="0,${-arrowLen} ${r * 0.45},${-r * 0.3} ${-r * 0.45},${-r * 0.3}"
          fill="white" opacity="0.95"/>
      </g>

      <!-- Small mower icon dot -->
      <circle cx="${cx}" cy="${cy}" r="${r * 0.3}"
        fill="white" opacity="0.9"/>
    `;
  }

  // ── Mow actions ───────────────────────────────────────────────────────────

  _startMode(mode) {
    const actions = {
      auto:     () => this._callService('lawn_mower', 'start_mowing'),
      edge:     () => this._callService('ecovacs', 'mow_edge', { entity_id: this._config.entity }),
      enhanced: () => this._callService('ecovacs', 'mow_enhanced', { entity_id: this._config.entity }),
    };
    const labels = { auto: 'Auto mow starting…', edge: 'Edge mow starting…', enhanced: 'Enhanced mow starting…' };
    this._toast(labels[mode] || 'Starting…');
    actions[mode]?.();
  }

  _startZoneMow(zoneId, mode = 'area') {
    const name = this._config.zone_names?.[zoneId] || `Zone ${zoneId}`;
    const modeLabels = { area: 'Area', edge: 'Edge', enhanced: 'Enhanced' };
    const modeLabel = modeLabels[mode] || 'Area';
    this._toast(`🌿 ${modeLabel} mow: ${name}…`);

    const serviceMap = {
      area:     { domain: 'ecovacs', service: 'mow_zone',     data: { entity_id: this._config.entity, zone_id: zoneId } },
      edge:     { domain: 'ecovacs', service: 'mow_edge',     data: { entity_id: this._config.entity, zone_id: zoneId } },
      enhanced: { domain: 'ecovacs', service: 'mow_enhanced', data: { entity_id: this._config.entity, zone_id: zoneId } },
    };
    const call = serviceMap[mode] || serviceMap.area;

    this._hass.callService(call.domain, call.service, call.data).catch(e => {
      console.error('ecovacs-mower-card: zone mow failed', e);
      this._toast('⚠️ Failed to start mow');
    });
  }

  _callService(domain, service, data = {}) {
    if (!this._hass) return;
    const payload = Object.keys(data).length ? data : { entity_id: this._config.entity };
    this._hass.callService(domain, service, payload).catch(e => {
      console.error(`ecovacs-mower-card: ${service} failed`, e);
      this._toast('⚠️ Command failed');
    });
  }

  // ── Status bar ────────────────────────────────────────────────────────────

  _updateStatusBar() {
    if (!this._hass) return;
    const state = this._hass.states[this._config.entity];
    if (!state) return;

    const info  = MOWER_STATES[state.state] || MOWER_STATES.idle;
    const attrs = state.attributes;
    const mowing = state.state === 'mowing';

    this.shadowRoot.getElementById('statusDot').style.background   = info.color;
    this.shadowRoot.getElementById('statusLabel').textContent       = `${info.icon} ${info.label}`;

    const parts = [];
    if (attrs.battery_level != null) parts.push(`🔋 ${attrs.battery_level}%`);
    if (attrs.mowed_area)            parts.push(`📐 ${attrs.mowed_area} m²`);
    this.shadowRoot.getElementById('statusMeta').textContent = parts.join('  ·  ');

    this.shadowRoot.getElementById('btnMow').disabled   = mowing;
    this.shadowRoot.getElementById('btnPause').disabled = !mowing;
    this.shadowRoot.getElementById('btnDock').disabled  = state.state === 'docked';
  }

  // ── Refresh ───────────────────────────────────────────────────────────────

  _startRefresh() {
    if (this._refreshTimer) return;
    const ms = (this._config.refresh_interval || 5) * 1000;
    this._refreshTimer = setInterval(() => this._loadMap(), ms);
  }

  _stopRefresh() {
    clearInterval(this._refreshTimer);
    this._refreshTimer = null;
  }

  // ── Toast ─────────────────────────────────────────────────────────────────

  _toast(msg, ms = 2500) {
    const t = this.shadowRoot.getElementById('toast');
    if (!t) return;
    clearTimeout(this._toastTimer);
    t.textContent = msg;
    t.classList.add('show');
    this._toastTimer = setTimeout(() => t.classList.remove('show'), ms);
  }

  connectedCallback() {
    setTimeout(() => { if (!this._mapLoaded && this._hass) this._loadMap(); }, 1000);
  }

  disconnectedCallback() { this._stopRefresh(); }
}

class EcovacsMowerCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
}

customElements.define('ecovacs-mower-card', EcovacsMowerCard);
customElements.define('ecovacs-mower-card-editor', EcovacsMowerCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ecovacs-mower-card',
  name: 'Ecovacs Mower Map',
  description: 'Interactive map card for the GOAT A3000 LiDAR mower',
  preview: true,
});

console.info(
  `%c ECOVACS-MOWER-CARD %c v${CARD_VERSION} `,
  'background:#4aff7b;color:#1a2a1a;font-weight:bold;padding:2px 6px;border-radius:3px 0 0 3px',
  'background:#1a2a1a;color:#4aff7b;font-weight:bold;padding:2px 6px;border-radius:0 3px 3px 0',
);
