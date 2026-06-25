'use strict';

// ── State ────────────────────────────────────────────────────────────────────
let drawMode = null;       // 'main' | 'zone' | null
let mainRegion = null;     // {x1,y1,x2,y2} normalized 0–1
let zones = [];            // [{id, name, rect:{x1,y1,x2,y2}}]
let nextZoneId = 1;
let drawing = false;
let drawStart = null;
let drawCurrent = null;

// ── Elements ─────────────────────────────────────────────────────────────────
const streamImg      = document.getElementById('stream-img');
const videoContainer = document.getElementById('video-container');
const canvas         = document.getElementById('draw-canvas');
const ctx            = canvas.getContext('2d');
const modeHint       = document.getElementById('mode-hint');
const statsList      = document.getElementById('stats-list');

// ── Canvas size sync ─────────────────────────────────────────────────────────
function syncCanvas() {
  const w = videoContainer.offsetWidth;
  const h = videoContainer.offsetHeight;
  if (w === 0 || h === 0) return;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width  = w;
    canvas.height = h;
    redrawCanvas();
  }
}

streamImg.addEventListener('load', syncCanvas);
window.addEventListener('resize', syncCanvas);
if (window.ResizeObserver) {
  new ResizeObserver(syncCanvas).observe(videoContainer);
}

// ── Canvas drawing ───────────────────────────────────────────────────────────
function getPos(e) {
  const r = canvas.getBoundingClientRect();
  return {
    x: (e.clientX - r.left) * (canvas.width  / r.width),
    y: (e.clientY - r.top)  * (canvas.height / r.height),
  };
}

function makeNormRect(a, b) {
  return {
    x1: Math.min(a.x, b.x) / canvas.width,
    y1: Math.min(a.y, b.y) / canvas.height,
    x2: Math.max(a.x, b.x) / canvas.width,
    y2: Math.max(a.y, b.y) / canvas.height,
  };
}

canvas.addEventListener('mousedown', e => {
  if (!drawMode) return;
  drawing   = true;
  drawStart = getPos(e);
  drawCurrent = { ...drawStart };
});

canvas.addEventListener('mousemove', e => {
  if (!drawing) return;
  drawCurrent = getPos(e);
  redrawCanvas();
});

canvas.addEventListener('mouseup', e => {
  if (!drawing) return;
  drawing     = false;
  drawCurrent = getPos(e);

  const rect = makeNormRect(drawStart, drawCurrent);
  const tooSmall = (rect.x2 - rect.x1) < 0.02 || (rect.y2 - rect.y1) < 0.02;

  if (!tooSmall) {
    if (drawMode === 'main') {
      mainRegion = rect;
      setMode(null);
    } else if (drawMode === 'zone') {
      const id = nextZoneId++;
      zones.push({ id, name: `Zone ${id}`, rect });
      // Stay in zone mode so user can keep adding zones
    }
  }
  redrawCanvas();
});

// Exit drawing mode if user clicks outside canvas
document.addEventListener('mouseup', () => {
  if (drawing) { drawing = false; redrawCanvas(); }
});

function redrawCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (mainRegion) drawRect(mainRegion, '#4f8ef7', 'Detection Area');
  zones.forEach(z => drawRect(z.rect, '#f5a623', z.name));
  if (drawing && drawStart && drawCurrent) {
    const rect  = makeNormRect(drawStart, drawCurrent);
    const color = drawMode === 'main' ? '#4f8ef7' : '#f5a623';
    drawRect(rect, color, null, true);
  }
}

function drawRect(rect, color, label, dashed = false) {
  const x = rect.x1 * canvas.width;
  const y = rect.y1 * canvas.height;
  const w = (rect.x2 - rect.x1) * canvas.width;
  const h = (rect.y2 - rect.y1) * canvas.height;

  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth   = 2;
  ctx.setLineDash(dashed ? [6, 4] : []);
  ctx.fillStyle   = color + '22';
  ctx.fillRect(x, y, w, h);
  ctx.strokeRect(x, y, w, h);

  if (label) {
    ctx.setLineDash([]);
    ctx.font      = 'bold 13px sans-serif';
    ctx.fillStyle = color;
    ctx.fillText(label, x + 5, y + 17);
  }
  ctx.restore();
}

// ── Mode buttons ─────────────────────────────────────────────────────────────
const mainRegionBtn  = document.getElementById('main-region-btn');
const addZoneBtn     = document.getElementById('add-zone-btn');
const undoZoneBtn    = document.getElementById('undo-zone-btn');
const clearBtn       = document.getElementById('clear-regions-btn');
const applyRegionBtn = document.getElementById('apply-regions-btn');

const HINTS = {
  main: 'Click and drag to draw the main detection area',
  zone: 'Click and drag to add a zone — repeat for each chair',
};

function setMode(mode) {
  drawMode = mode;
  mainRegionBtn.classList.toggle('active', mode === 'main');
  addZoneBtn.classList.toggle('active',    mode === 'zone');
  if (mode) {
    modeHint.textContent = HINTS[mode];
    modeHint.classList.add('visible');
    canvas.style.cursor = 'crosshair';
  } else {
    modeHint.classList.remove('visible');
    canvas.style.cursor = 'default';
  }
}

mainRegionBtn.addEventListener('click', () => setMode(drawMode === 'main' ? null : 'main'));
addZoneBtn.addEventListener('click',    () => setMode(drawMode === 'zone' ? null : 'zone'));

undoZoneBtn.addEventListener('click', () => {
  if (zones.length) {
    zones.pop();
    nextZoneId = zones.length > 0 ? Math.max(...zones.map(z => z.id)) + 1 : 1;
    redrawCanvas();
  }
});

clearBtn.addEventListener('click', async () => {
  if (!confirm('Clear all regions and zones?')) return;
  mainRegion = null;
  zones      = [];
  nextZoneId = 1;
  setMode(null);
  redrawCanvas();
  await fetch('/api/regions', { method: 'DELETE' });
  showToast('Regions cleared');
});

applyRegionBtn.addEventListener('click', async () => {
  const payload = {
    main_region: mainRegion
      ? [mainRegion.x1, mainRegion.y1, mainRegion.x2, mainRegion.y2]
      : null,
    zones: zones.map(z => ({
      id:   z.id,
      name: z.name,
      rect: [z.rect.x1, z.rect.y1, z.rect.x2, z.rect.y2],
    })),
  };
  const resp = await fetch('/api/regions', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  });
  if (resp.ok) {
    setMode(null);
    showToast('Regions applied');
    await loadRegions();  // reload so canvas stays in sync with what was applied
  }
});

// ── Camera settings ───────────────────────────────────────────────────────────
const cameraSelect     = document.getElementById('camera-select');
const resolutionSelect = document.getElementById('resolution-select');
const applyCameraBtn   = document.getElementById('apply-camera-btn');
const modeWebcamBtn    = document.getElementById('mode-webcam-btn');
const modeUrlBtn       = document.getElementById('mode-url-btn');
const webcamControls   = document.getElementById('webcam-controls');
const urlControls      = document.getElementById('url-controls');
const cameraUrlInput   = document.getElementById('camera-url');

let cameraMode = 'webcam'; // 'webcam' | 'url'

function setCameraMode(mode) {
  cameraMode = mode;
  modeWebcamBtn.classList.toggle('active', mode === 'webcam');
  modeUrlBtn.classList.toggle('active',    mode === 'url');
  webcamControls.style.display = mode === 'webcam' ? '' : 'none';
  urlControls.style.display    = mode === 'url'    ? '' : 'none';
}

modeWebcamBtn.addEventListener('click', () => setCameraMode('webcam'));
modeUrlBtn.addEventListener('click',    () => setCameraMode('url'));

async function loadCameras() {
  const resp    = await fetch('/api/cameras');
  const cameras = await resp.json();
  cameraSelect.innerHTML = '';
  if (cameras.length === 0) {
    cameraSelect.innerHTML = '<option value="">No cameras found</option>';
    return;
  }
  const savedSrc = INITIAL_STATE.camera_source;
  cameras.forEach(i => {
    const opt       = document.createElement('option');
    opt.value       = i;
    opt.textContent = `Camera ${i}`;
    if (i === savedSrc) opt.selected = true;
    cameraSelect.appendChild(opt);
  });
}

// Restore saved state
(function initCameraUI() {
  const src = INITIAL_STATE.camera_source;
  if (typeof src === 'string' && src !== '') {
    setCameraMode('url');
    cameraUrlInput.value = src;
  } else {
    setCameraMode('webcam');
    const savedRes  = `${INITIAL_STATE.width}x${INITIAL_STATE.height}`;
    const savedOpt  = resolutionSelect.querySelector(`option[value="${savedRes}"]`);
    if (savedOpt) savedOpt.selected = true;
  }
})();

applyCameraBtn.addEventListener('click', async () => {
  let body;
  if (cameraMode === 'url') {
    const url = cameraUrlInput.value.trim();
    if (!url) { showToast('Please enter a stream URL'); return; }
    body = { source: url };
  } else {
    const [w, h] = resolutionSelect.value.split('x').map(Number);
    body = { source: parseInt(cameraSelect.value, 10), width: w, height: h };
  }
  const resp = await fetch('/api/camera', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  const data = await resp.json();
  if (data.ok) {
    const aw = data.actual_width, ah = data.actual_height;
    if (cameraMode === 'url') {
      showToast(`IP camera connected — ${aw}×${ah}`);
    } else {
      const req = `${body.width}×${body.height}`, act = `${aw}×${ah}`;
      showToast(req === act ? `Resolution set to ${act}` : `Requested ${req} → camera set ${act}`);
    }
  } else {
    showToast(`Error: ${data.error}`);
  }
});

// ── Confidence sliders ────────────────────────────────────────────────────────
const phoneSlider  = document.getElementById('phone-conf');
const personSlider = document.getElementById('person-conf');
const phoneVal     = document.getElementById('phone-conf-val');
const personVal    = document.getElementById('person-conf-val');

let _confTimer = null;

function initSliders() {
  phoneSlider.value  = Math.round(INITIAL_STATE.phone_conf  * 100);
  personSlider.value = Math.round(INITIAL_STATE.person_conf * 100);
  phoneVal.textContent  = `${phoneSlider.value}%`;
  personVal.textContent = `${personSlider.value}%`;
}

function onSliderChange() {
  phoneVal.textContent  = `${phoneSlider.value}%`;
  personVal.textContent = `${personSlider.value}%`;
  clearTimeout(_confTimer);
  _confTimer = setTimeout(async () => {
    await fetch('/api/confidence', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        phone_conf:  parseFloat(phoneSlider.value)  / 100,
        person_conf: parseFloat(personSlider.value) / 100,
      }),
    });
  }, 300);  // debounce — send only after slider stops moving
}

phoneSlider.addEventListener('input',  onSliderChange);
personSlider.addEventListener('input', onSliderChange);
initSliders();

// ── Model switching ───────────────────────────────────────────────────────────
const modelSelect    = document.getElementById('model-select');
const applyModelBtn  = document.getElementById('apply-model-btn');

// Pre-select saved model
(function initModelUI() {
  const opt = modelSelect.querySelector(`option[value="${INITIAL_STATE.model_name}"]`);
  if (opt) opt.selected = true;
})();

applyModelBtn.addEventListener('click', async () => {
  const name = modelSelect.value;
  applyModelBtn.disabled   = true;
  applyModelBtn.textContent = 'Loading…';
  const resp = await fetch('/api/model', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ model: name }),
  });
  applyModelBtn.disabled   = false;
  applyModelBtn.textContent = 'Apply Model';
  const data = await resp.json();
  showToast(data.ok ? `Model switched to ${data.model}` : `Error: ${data.error}`);
});

// ── Stats ─────────────────────────────────────────────────────────────────────
const resetStatsBtn = document.getElementById('reset-stats-btn');

function formatTime(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

function updateStats(stats) {
  if (stats.length === 0) {
    statsList.innerHTML = '<p class="empty-msg">No zones defined yet.</p>';
    return;
  }

  const validIds = new Set(stats.map(z => `stat-${z.id}`));
  // Remove stale items
  Array.from(statsList.children).forEach(el => {
    if (!validIds.has(el.id)) el.remove();
  });

  stats.forEach(zone => {
    let item = document.getElementById(`stat-${zone.id}`);
    if (!item) {
      item = document.createElement('div');
      item.id        = `stat-${zone.id}`;
      item.className = 'stat-item';
      item.innerHTML = `
        <div class="zone-header">
          <span class="indicator" id="ind-${zone.id}"></span>
          <span class="zone-name">${zone.name}</span>
        </div>
        <div class="zone-time" id="time-${zone.id}">00:00:00</div>
        <div class="zone-sessions" id="sess-${zone.id}">0 sessions</div>
      `;
      statsList.appendChild(item);
    }

    document.getElementById(`ind-${zone.id}`).className =
      'indicator' + (zone.is_active ? ' active' : '');
    item.className =
      'stat-item' + (zone.is_active ? ' active' : '');
    document.getElementById(`time-${zone.id}`).textContent =
      formatTime(zone.total_seconds);
    document.getElementById(`sess-${zone.id}`).textContent =
      `${zone.sessions} session${zone.sessions !== 1 ? 's' : ''}`;
  });
}

resetStatsBtn.addEventListener('click', async () => {
  await fetch('/api/stats/reset', { method: 'POST' });
  showToast('Timers reset');
});

// ── Toast ─────────────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg) {
  const toast     = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('visible');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toast.classList.remove('visible'), 2200);
}

// ── Load existing regions on startup ─────────────────────────────────────────
async function loadRegions() {
  const resp = await fetch('/api/regions');
  const data = await resp.json();
  if (data.main_region) {
    const [x1, y1, x2, y2] = data.main_region;
    mainRegion = { x1, y1, x2, y2 };
  }
  if (data.zones && data.zones.length) {
    zones = data.zones.map(z => ({
      id:   z.id,
      name: z.name,
      rect: { x1: z.rect[0], y1: z.rect[1], x2: z.rect[2], y2: z.rect[3] },
    }));
    nextZoneId = Math.max(...zones.map(z => z.id)) + 1;
  }
  redrawCanvas();
}

// ── Polling ───────────────────────────────────────────────────────────────────
setInterval(async () => {
  try {
    const resp  = await fetch('/api/stats');
    const stats = await resp.json();
    updateStats(stats);
  } catch (_) { /* ignore if server busy */ }
}, 1000);

// ── Init ──────────────────────────────────────────────────────────────────────
loadCameras();
loadRegions();
syncCanvas();

