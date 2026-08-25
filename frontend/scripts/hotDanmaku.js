// High-energy danmaku fly-screen renderer.
// Pure circular queue + lane scheduler: no wave switching, no control UI.
(() => {
  const PUMP_MS = 92;
  const LANE_GAP_MS = 260;
  const BASE_DURATION_MS = 11800;
  const DURATION_JITTER_MS = 3600;
  const EXTRA_TRAVEL_PX = 760;
  const WARMUP_PER_LANE = 1;

  const state = {
    queue: [],
    lanes: [],
    timer: null,
    reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    rand: Math.random,
  };

  const getEls = () => ({
    layer: $('#hot-danmaku-layer'),
    stage: $('#hot-danmaku-stage'),
  });

  const seedRand = (seed) => {
    let s = seed >>> 0;
    return () => {
      s = (Math.imul(1664525, s) + 1013904223) >>> 0;
      return s / 4294967296;
    };
  };

  const shuffle = (items, rand) => {
    const arr = items.slice();
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  };

  const clearTimer = () => {
    if (state.timer) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
  };

  const ensureShell = () => {
    const { stage } = getEls();
    if (!stage || stage.dataset.shellReady === '1') return;
    stage.innerHTML = `
      <div class="hot-danmaku-grid" aria-hidden="true"></div>
      <div class="hot-danmaku-halo" aria-hidden="true"></div>
    `;
    stage.dataset.shellReady = '1';
  };

  const clearItems = () => {
    const { stage } = getEls();
    if (!stage) return;
    $$('.hot-danmaku-item', stage).forEach(el => el.remove());
  };

  const viewportRect = () => {
    const { stage } = getEls();
    return stage?.getBoundingClientRect() || {
      width: window.innerWidth,
      height: Math.max(260, window.innerHeight * 0.5),
    };
  };

  const laneCount = () => {
    const h = viewportRect().height || 300;
    return Math.max(8, Math.min(14, Math.round(h / 34)));
  };

  const resetLanes = () => {
    const count = laneCount();
    state.lanes = Array.from({ length: count }, (_, lane) => ({
      lane,
      nextAt: 0,
    }));
  };

  const activeLimit = () => {
    const count = Math.max(1, state.lanes.length || laneCount());
    return count * (window.innerWidth < 720 ? 3 : 5);
  };

  const buildQueue = (D) => {
    const peaks = Array.isArray(D?.hotDanmaku) ? D.hotDanmaku : [];
    const items = [];
    const seen = new Set();

    peaks.forEach((peak, peakIndex) => {
      const texts = Array.isArray(peak?.items) ? peak.items : [];
      texts.forEach((raw, itemIndex) => {
        const text = String(raw || '').trim();
        if (!text) return;
        const key = text.replace(/\s+/g, ' ');
        if (seen.has(key)) return;
        seen.add(key);
        items.push({ text, peakIndex, itemIndex, tm: peak?.tm || '' });
      });
    });

    if (!items.length) {
      peaks.forEach((peak, peakIndex) => {
        const fallback = String(peak?.s || peak?.tm || '高能弹幕').trim();
        if (fallback) items.push({ text: fallback, peakIndex, itemIndex: 0, tm: peak?.tm || '' });
      });
    }

    const seed = hashString(items.map(x => `${x.tm}:${x.text}`).join('|') || 'hot-danmaku');
    state.rand = seedRand(seed);
    state.queue = shuffle(items, state.rand);
  };

  const popQueue = () => {
    const item = state.queue.shift();
    if (!item) return null;
    return item;
  };

  const pushQueue = (item) => {
    if (item?.text) state.queue.push(item);
  };

  const laneTop = (laneIndex) => {
    const r = viewportRect();
    const count = Math.max(1, state.lanes.length || laneCount());
    const gap = (r.height || 300) / count;
    const jitter = (state.rand() * 2 - 1) * Math.min(5, gap * 0.14);
    return laneIndex * gap + gap * 0.5 + jitter;
  };

  const pickLane = () => {
    const now = performance.now();
    const free = state.lanes.filter(lane => lane.nextAt <= now);
    if (free.length) {
      free.sort((a, b) => a.nextAt - b.nextAt);
      return free[0];
    }
    const cooled = state.lanes.filter(lane => lane.nextAt <= now + 120);
    if (cooled.length) {
      cooled.sort((a, b) => a.nextAt - b.nextAt);
      return cooled[0];
    }
    return null;
  };

  const spawnOnLane = (lane, { warmup = false, startOffset: forcedStartOffset = 0 } = {}) => {
    const { stage } = getEls();
    if (!stage || !lane || !state.queue.length) return false;

    const item = popQueue();
    if (!item) return false;

    const r = viewportRect();
    const travel = Math.round((r.width || window.innerWidth) + EXTRA_TRAVEL_PX + state.rand() * 220);
    const baseDuration = BASE_DURATION_MS + state.rand() * DURATION_JITTER_MS;
    const durationMs = warmup ? baseDuration * (0.66 + state.rand() * 0.18) : baseDuration;
    const textWidth = Math.max(120, item.text.length * 18);
    const drift = ((state.rand() * 2 - 1) * 8).toFixed(1);
    const scale = (0.90 + Math.min(0.30, item.text.length / 42 * 0.10 + (state.rand() > 0.76 ? 0.04 : 0))).toFixed(2);
    const accent = state.rand() > 0.52 ? 'rgba(0,174,236,.16)' : 'rgba(251,114,153,.16)';
    const glow = state.rand() > 0.64 ? 'rgba(255,255,255,.16)' : 'rgba(255,255,255,.10)';
    const startOffset = warmup
      ? Math.round(forcedStartOffset || Math.min(travel * 0.7, (r.width || window.innerWidth) * (0.18 + state.rand() * 0.54)))
      : 0;

    const el = document.createElement('span');
    el.className = 'hot-danmaku-item';
    if (warmup && startOffset > 0) {
      el.classList.add('is-warmup');
      el.style.setProperty('--start-offset', `${startOffset}px`);
    }
    el.style.setProperty('--top', `${laneTop(lane.lane).toFixed(1)}px`);
    el.style.setProperty('--dur', `${(durationMs / 1000).toFixed(2)}s`);
    el.style.setProperty('--delay', '0s');
    el.style.setProperty('--scale', scale);
    el.style.setProperty('--travel', `${travel}px`);
    el.style.setProperty('--drift', `${drift}px`);
    el.style.setProperty('--accent', accent);
    el.style.setProperty('--glow', glow);
    el.textContent = item.text;

    lane.nextAt = performance.now() + durationMs + LANE_GAP_MS;

    el.addEventListener('animationend', () => {
      el.remove();
      pushQueue(item); // queue loop: finished danmaku goes to the tail
    }, { once: true });

    stage.appendChild(el);
    return true;
  };

  const warmFill = () => {
    if (!state.queue.length) return;
    const r = viewportRect();
    const lanes = state.lanes.length ? state.lanes : (resetLanes(), state.lanes);
    lanes.forEach((lane, i) => {
      for (let k = 0; k < WARMUP_PER_LANE; k++) {
        const base = ((k + 0.32 + state.rand() * 0.16) / WARMUP_PER_LANE) * (r.width || window.innerWidth);
        const ok = spawnOnLane(lane, { warmup: true, startOffset: base });
        if (!ok) break;
      }
      lane.nextAt = performance.now() + i * 85 + state.rand() * 140;
    });
  };

  const pump = () => {
    if (!state.queue.length) return;
    const { stage } = getEls();
    const active = stage ? $$('.hot-danmaku-item', stage).length : 0;
    if (active >= activeLimit()) return;
    const now = performance.now();
    state.lanes.forEach(lane => {
      if (lane.nextAt <= now && (stage ? $$('.hot-danmaku-item', stage).length : 0) < activeLimit()) {
        spawnOnLane(lane);
      }
    });
  };

  function renderHotDanmaku(D) {
    const { layer, stage } = getEls();
    if (!layer || !stage) return;

    clearTimer();
    ensureShell();
    clearItems();
    resetLanes();
    buildQueue(D);

    if (!state.queue.length) {
      layer.classList.add('hide');
      layer.classList.remove('is-live');
      return;
    }

    layer.classList.remove('hide');
    layer.classList.add('is-live');

    if (state.reducedMotion) {
      warmFill();
      return;
    }

    warmFill();
    state.timer = window.setInterval(pump, PUMP_MS);
  }

  function hideHotDanmaku() {
    const { layer, stage } = getEls();
    clearTimer();
    state.queue = [];
    state.lanes = [];
    layer?.classList.add('hide');
    layer?.classList.remove('is-live');
    if (stage) {
      stage.innerHTML = '';
      stage.dataset.shellReady = '0';
    }
  }

  function refreshHotDanmaku() {
    if (!state.queue.length) return;
    pump();
  }

  window.renderHotDanmaku = renderHotDanmaku;
  window.refreshHotDanmaku = refreshHotDanmaku;
  window.hideHotDanmaku = hideHotDanmaku;

  window.addEventListener('beforeunload', clearTimer);
})();
