// Danmaku theme heatmap drill-down.
function buildDmHeatModel(themes, peaks, duration){
  const totalDuration = Math.max(Number(duration) || 0, 60);
  const sourceThemes = (themes || [])
    .map((theme, sourceIdx) => {
      const win = parseThemeWindow(theme.t, totalDuration);
      return {
        theme,
        sourceIdx,
        win,
      };
    })
    .sort((a, b) => (b.theme.c || 0) - (a.theme.c || 0));

  const total = sourceThemes.reduce((sum, item) => sum + (Number(item.theme.c) || 0), 0);
  const bucketCount = clamp(Math.round(totalDuration / 32), 28, 48);
  const bucketSec = totalDuration / bucketCount;
  const buckets = Array.from({ length: bucketCount }, (_, idx) => ({
    idx,
    start: idx * bucketSec,
    end: (idx + 1) * bucketSec,
    score: 0,
    tops: [],
    peak: null,
  }));

  const rows = sourceThemes.map((item, rowIdx) => {
    const { theme, sourceIdx, win } = item;
    const idx = rowIdx;
    const color = themePalette(rowIdx);
    const share = total ? (Number(theme.c) || 0) / total : 0;
    const cells = Array.from({ length: bucketCount }, () => 0);
    let peakHits = 0;

    if (win) {
      const span = Math.max(1, win.end - win.start);
      const startIndex = clamp(Math.floor(win.start / bucketSec), 0, bucketCount - 1);
      const endIndex = clamp(Math.ceil(win.end / bucketSec) - 1, 0, bucketCount - 1);
      for (let bi = startIndex; bi <= endIndex; bi++) {
        const bucket = buckets[bi];
        const overlap = Math.max(0, Math.min(bucket.end, win.end) - Math.max(bucket.start, win.start));
        if (overlap <= 0) continue;
        const normalized = overlap / bucketSec;
        const weighted = normalized * (0.42 + share * 1.28);
        cells[bi] = weighted;
        bucket.score += weighted;
        bucket.tops.push({ idx, score: weighted });
      }
      peakHits = (peaks || []).filter(p => {
        const sec = hms2sec(p.tm);
        return sec >= win.start && sec <= win.end;
      }).length;
    } else {
      const middle = Math.floor(bucketCount / 2);
      cells[middle] = 0.22 + share * 0.4;
      buckets[middle].score += cells[middle];
      buckets[middle].tops.push({ idx, score: cells[middle] });
    }

    const rowMax = Math.max(...cells, 1);
    const normalizedCells = cells.map(v => v / rowMax);

    return { theme, idx, sourceIdx, win, color, share, cells: normalizedCells, peakHits };
  });

  const overviewMax = Math.max(...buckets.map(b => b.score), 1);
  buckets.forEach(bucket => {
    bucket.score = bucket.score / overviewMax;
    bucket.tops.sort((a, b) => b.score - a.score);
    bucket.top = bucket.tops.slice(0, 3);
    const peak = (peaks || []).find(p => {
      const sec = hms2sec(p.tm);
      return sec >= bucket.start && sec < bucket.end;
    });
    bucket.peak = peak || null;
  });

  return { totalDuration, bucketCount, bucketSec, total, rows, buckets };
}

function renderDmDrill(themes, peaks, duration){
  const Dr = $('#drill');
  const model = buildDmHeatModel(themes, peaks, duration);
  const list = model.rows;
  if(!list.length){
    Dr.innerHTML = `<h2>弹幕反馈</h2><div class="dm-empty">暂无可展示的弹幕主题。</div>`;
    return;
  }

  const top = list[0];
  const heatHintDefault = `将鼠标移到热区或主题带上，查看对应时段与关联主题。`;
  const overviewCells = model.buckets.map(bucket => {
    const h = 16 + Math.round(88 * Math.pow(bucket.score, 0.85));
    const color = hexToRgba('#fb7299', 0.12 + bucket.score * 0.76);
    const label = `${fmtDur(bucket.start)} — ${fmtDur(bucket.end)}`;
    return `<button type="button" class="dm-heat-cell" data-bucket-index="${bucket.idx}" aria-label="${escapeHtml(label)}" style="--h:${h}%;--c:${color}"></button>`;
  }).join('');

  const axisMarks = [0, 0.25, 0.5, 0.75, 1].map((f, i) => {
    const sec = model.totalDuration * f;
    return `<span>${escapeHtml(fmtDur(sec))}</span>`;
  }).join('');

  const bandRows = list.map((item, idx) => {
    const windowLabel = fmtThemeWindowLabel(item.win, model.totalDuration);
    const cells = item.cells.map((v, bi) => {
      const alpha = 0.10 + v * 0.82;
      return `<span class="dm-band-cell" style="background:${hexToRgba(item.color, alpha)}"></span>`;
    }).join('');
    return `<button type="button" class="dm-band-row" data-anchor="dm-${item.sourceIdx}" data-dm-index="${idx}" aria-pressed="false">
      <span class="dm-band-label">
        <span class="name">${escapeHtml(item.theme.n || `主题${idx + 1}`)}</span>
        <span class="meta">${escapeHtml(windowLabel)} · ${item.peakHits ? item.peakHits + ' 个峰值重叠' : '峰值较少'}</span>
      </span>
      <span class="dm-band-track" style="--cols:${model.bucketCount}">${cells}</span>
      <span class="dm-band-meta"><b>${item.theme.c}</b><em>${fmtThemeShare(item.theme.c, model.total)}</em></span>
    </button>`;
  }).join('');

  const peaksHtml = (peaks || []).slice(0, 4).map((p, idx) => {
    const bucketIndex = clamp(Math.floor(hms2sec(p.tm) / model.bucketSec), 0, model.bucketCount - 1);
    return `<button type="button" class="dm-peak-item" data-bucket-index="${bucketIndex}">
      <div class="tm">${escapeHtml(p.tm)} · ${escapeHtml(p.x)}</div>
      <div class="desc">${escapeHtml(p.s || '弹幕密度在此处出现明显抬升')}</div>
    </button>`;
  }).join('');

  const shortcutHtml = list.slice(0, 6).map((item, idx) => `
    <button type="button" class="dm-mini" data-dm-index="${idx}">${escapeHtml(item.theme.n || `主题${idx + 1}`)} · ${item.theme.c}</button>
  `).join('');

  Dr.innerHTML = `
    <h2>弹幕反馈</h2>
    <div class="dm-shell">
      <section class="dm-panel dm-main">
        <div class="dm-panel-head">
          <div>
            <h3>时间热力图</h3>
          </div>
          <div class="tiny">${list.length} 个主题 · ${model.total} 条弹幕</div>
        </div>

        <div class="dm-heat-card">
          <div class="dm-heat-head">
            <div>
              <div class="dm-heat-kicker">Time Heatmap</div>
              <div class="dm-heat-title">弹幕时间热力图</div>
            </div>
            <div class="dm-heat-hint" id="dm-heat-hint">${heatHintDefault}</div>
          </div>
          <div class="dm-heat-grid" style="--cols:${model.bucketCount}">
            ${overviewCells}
          </div>
          <div class="dm-time-axis">${axisMarks}</div>
        </div>

        <div class="dm-band-card">
          <div class="dm-band-head">
            <div>
              <div class="k">Theme Bands</div>
              <div class="s">每一行是一条主题带，颜色越深代表越集中。</div>
            </div>
            <div class="tiny">点击任意一行即可聚焦</div>
          </div>
          <div class="dm-band-list">
            ${bandRows}
          </div>
        </div>
      </section>

      <aside class="dm-panel dm-side">
        <div class="dm-panel-head">
          <div>
            <h3>主题聚焦</h3>
            <p>当前高频主题与峰值摘要。</p>
          </div>
        </div>

        <div class="dm-summary-grid">
          <div class="dm-stat"><span>主题总数</span><strong>${list.length}</strong><em>已聚类</em></div>
          <div class="dm-stat"><span>弹幕总量</span><strong>${model.total}</strong><em>主题累计</em></div>
          <div class="dm-stat"><span>最热主题</span><strong>${escapeHtml(top.theme.n || '—')}</strong><em>${top.theme.c} 条</em></div>
        </div>

        <div class="dm-focus" id="dm-focus" aria-live="polite"></div>

        <div class="dm-shortcuts" aria-label="快速切换主题">
          ${shortcutHtml}
        </div>

        <div class="dm-peak-list">
          ${(peaks || []).slice(0, 4).map((p, idx) => {
            const bucketIndex = clamp(Math.floor(hms2sec(p.tm) / model.bucketSec), 0, model.bucketCount - 1);
            return `<button type="button" class="dm-peak-item" data-bucket-index="${bucketIndex}">
              <div class="tm">${escapeHtml(p.tm)} · ${escapeHtml(p.x)}</div>
              <div class="desc">${escapeHtml(p.s || '弹幕密度在此处出现明显抬升')}</div>
            </button>`;
          }).join('')}
        </div>
      </aside>
    </div>`;

  const heatHint = Dr.querySelector('#dm-heat-hint');
  const focus = Dr.querySelector('#dm-focus');
  const bandRowsEls = [...Dr.querySelectorAll('.dm-band-row[data-dm-index]')];
  const heatCells = [...Dr.querySelectorAll('.dm-heat-cell[data-bucket-index]')];
  const miniBtns = [...Dr.querySelectorAll('.dm-mini[data-dm-index]')];
  const peakBtns = [...Dr.querySelectorAll('.dm-peak-item[data-bucket-index]')];

  const applyHeatHint = (bucketIndex) => {
    const bucket = model.buckets[bucketIndex];
    if(!bucket || !heatHint) return;
    const range = `${fmtDur(bucket.start)} — ${fmtDur(bucket.end)}`;
    const topNames = bucket.top.slice(0, 3).map(x => escapeHtml(list[x.idx].theme.n || `主题${x.idx + 1}`)).join(' · ');
    heatHint.innerHTML = `<b>${escapeHtml(range)}</b> · 热度 ${Math.round(bucket.score * 100)} · ${topNames || '暂无明显重叠主题'}`;
  };

  const selectTheme = (index) => {
    const item = model.rows[index];
    if(!item || !focus) return;
    const win = item.win;
    bandRowsEls.forEach(el => {
      const on = Number(el.dataset.dmIndex) === index;
      el.classList.toggle('active', on);
      el.setAttribute('aria-pressed', String(on));
    });
    miniBtns.forEach(el => el.classList.toggle('active', Number(el.dataset.dmIndex) === index));
    heatCells.forEach(el => {
      const bi = Number(el.dataset.bucketIndex);
      const bucket = model.buckets[bi];
      const on = !!(win && bucket && Math.max(0, Math.min(bucket.end, win.end) - Math.max(bucket.start, win.start)) > 0);
      el.classList.toggle('active', on);
      el.classList.toggle('dim', !!win && !on);
    });
    focus.innerHTML = `
      <h4>${escapeHtml(item.theme.n || `主题${index + 1}`)}</h4>
      <div class="sub">${item.theme.c} 条弹幕 · 占比 ${fmtThemeShare(item.theme.c, model.total)} · ${escapeHtml(fmtThemeWindowLabel(win, model.totalDuration))}</div>
      <div class="dm-focus-grid">
        <div class="dm-focus-chip"><span>集中时段</span>${escapeHtml(item.theme.t || '未知')}</div>
        <div class="dm-focus-chip"><span>峰值重叠</span>${item.peakHits} 个峰值</div>
        <div class="dm-focus-chip"><span>视频占比</span>${fmtThemeShare(item.theme.c, model.total)}</div>
        <div class="dm-focus-chip"><span>主题色</span>${item.color}</div>
      </div>
      `;
    if(heatHint) {
      applyHeatHint(index >= 0 ? clamp(Math.floor((win ? win.start : 0) / model.bucketSec), 0, model.bucketCount - 1) : 0);
    }
  };

  bandRowsEls.forEach(el => {
    const index = Number(el.dataset.dmIndex);
    el.addEventListener('mouseenter', () => selectTheme(index));
    el.addEventListener('focus', () => selectTheme(index));
    el.addEventListener('click', () => selectTheme(index));
  });

  miniBtns.forEach(el => {
    const index = Number(el.dataset.dmIndex);
    el.addEventListener('click', () => selectTheme(index));
    el.addEventListener('mouseenter', () => selectTheme(index));
  });

  peakBtns.forEach(el => {
    const bucketIndex = Number(el.dataset.bucketIndex);
    el.addEventListener('mouseenter', () => applyHeatHint(bucketIndex));
    el.addEventListener('focus', () => applyHeatHint(bucketIndex));
    el.addEventListener('click', () => {
      applyHeatHint(bucketIndex);
      const bucket = model.buckets[bucketIndex];
      const primary = bucket && bucket.top && bucket.top[0] ? bucket.top[0].idx : 0;
      selectTheme(primary);
    });
  });

  heatCells.forEach(el => {
    const bucketIndex = Number(el.dataset.bucketIndex);
    el.addEventListener('mouseenter', () => applyHeatHint(bucketIndex));
    el.addEventListener('focus', () => applyHeatHint(bucketIndex));
    el.addEventListener('click', () => {
      applyHeatHint(bucketIndex);
      const bucket = model.buckets[bucketIndex];
      const primary = bucket && bucket.top && bucket.top[0] ? bucket.top[0].idx : 0;
      selectTheme(primary);
    });
  });

  selectTheme(0);
}
