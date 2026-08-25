// Word cloud normalisation, rendering and detail interactions.
function normalizeWordList(D, src){
  const wc = D.wordcloud || D.wordClouds || {};
  const raw = src === 'dm'
    ? (wc.dm || wc.danmaku || [])
    : (wc.cm || wc.comment || []);
  return (raw || []).map(x=>({
    w: String(x.w || x.t || '').trim(),
    c: Number(x.c || 0),
    s: Array.isArray(x.s) ? x.s : []
  })).filter(x=>x.w && x.c >= 0);
}

// 当前仓库版词云：使用自然换行的标签流，不做绝对定位，避免词挤在中间重叠。
function layoutCloud(stageEl, words, kind){
  if(!stageEl) return;
  const detail = kind === 'dm' ? $('#dm-wordcloud-detail') : $('#cm-wordcloud-detail');
  stageEl.innerHTML = '';
  if(detail){ detail.classList.remove('on'); detail.innerHTML = ''; }
  if(!words || !words.length){
    stageEl.innerHTML = '<div class="cloud-empty">暂无可展示的词云数据</div>';
    return;
  }

  const list = words.slice(0, 80);
  const counts = list.map(w=>Number(w.c)||0);
  const max = Math.max(...counts, 1);
  const min = Math.min(...counts, max);
  const span = Math.max(max - min, 1);

  // 打散顺序，避免高频词全部堆在左上，同时 flex 排版不会互相覆盖。
  const shuffled = list.map((w,i)=>({w, o:(i*2654435761)%list.length}))
                       .sort((a,b)=>a.o-b.o).map(x=>x.w);

  stageEl.innerHTML = shuffled.map(item=>{
    const ratio = ((Number(item.c)||0) - min) / span;
    const size = Math.round(12 + ratio * 26);
    const level = ratio > 0.66 ? 1 : ratio > 0.33 ? 2 : ratio > 0.1 ? 3 : 4;
    return `<button type="button" class="cloud-word wc-l${level}" style="font-size:${size}px"
      data-kind="${kind}" data-word="${encodeURIComponent(item.w)}"
      title="出现 ${item.c} 次">${escapeHtml(item.w)}<span class="cnt">${item.c}</span></button>`;
  }).join('');

  stageEl.querySelectorAll('.cloud-word').forEach(el=>el.onclick=()=>{
    const word = decodeURIComponent(el.dataset.word || '');
    const hit = words.find(x=>x.w === word);
    if(!hit || !detail) return;
    stageEl.querySelectorAll('.cloud-word').forEach(x=>x.classList.toggle('active', x === el));
    const label = kind === 'dm' ? '弹幕' : '评论';
    const icon = kind === 'dm' ? '💬' : '🧵';
    const examples = (hit.s||[]).map(s=>`<li>${escapeHtml(s)}</li>`).join('') || '<li class="muted">旧缓存没有原文样例，重新分析后可显示。</li>';
    detail.innerHTML = `<h4><span>${icon}</span>「${escapeHtml(word)}」出现在 ${hit.c} 条${label}中</h4><ul>${examples}</ul>`;
    detail.classList.add('on');
  });
}

function renderWordClouds(D){
  const dm = normalizeWordList(D, 'dm');
  const cm = normalizeWordList(D, 'cm');
  const dmEl = $('#dm-wordcloud');
  const cmEl = $('#cm-wordcloud');
  if($('#dm-wordcloud-sub')) $('#dm-wordcloud-sub').textContent = dm.length ? `${dm.length} 个高频词` : '暂无词云';
  if($('#cm-wordcloud-sub')) $('#cm-wordcloud-sub').textContent = cm.length ? `${cm.length} 个高频词` : '暂无词云';
  layoutCloud(dmEl, dm, 'dm');
  layoutCloud(cmEl, cm, 'cm');
}
