// Main report rendering and insight navigation.
function render(D){
  const v = D.video, R = $('#result');
  R.classList.remove('hide');
  $('#vtitle').textContent = v.title;
  $('#vup').textContent = v.up;

  // B站图片有防盗链，必须去掉 Referer 才能加载
  const cov = $('#vcover');
  if(v.cover){
    cov.innerHTML = `<img src="${v.cover}" referrerpolicy="no-referrer" alt="视频封面"
      onerror="this.parentNode.textContent='封面'">`;
  }else{
    cov.textContent = '封面';
  }

  $('#s-play').textContent = v.play;
  $('#s-dm').textContent = v.dm.toLocaleString();
  $('#s-cm').textContent = v.cm.toLocaleString();
  $('#s-cost').textContent = (D.meta && D.meta.elapsed) ? D.meta.elapsed + 's' : '-';

  // 动态计算卡片摘要
  const dmCount = D.dmThemes ? D.dmThemes.length : 0;
  const pkCount = D.peaks ? D.peaks.length : 0;
  const cmCount = D.cmThemes ? D.cmThemes.length : 0;
  const actCount = D.acts ? D.acts.length : 0;
  const topPeak = D.peaks && D.peaks[0] ? `${D.peaks[0].tm} 密度达${D.peaks[0].x}` : '-';
  const hiDisCount = D.cmThemes ? D.cmThemes.filter(t=>t.dis==='高').length : 0;

  const cards=[
    {k:'dm', i:'✦', t:'弹幕反馈', b:dmCount+' 个主题', p:D.dmThemes&&D.dmThemes[0]?`点开看「${D.dmThemes[0].n}」的交互分布图`:'-'},
    {k:'pk', i:'↯', t:'高能时刻', b:'TOP '+pkCount+' 片段', p:topPeak},
    {k:'cm', i:'◐', t:'评论总结', b:cmCount+' 个主题', p:hiDisCount?`含 ${hiDisCount} 个高争议主题`:`${cmCount} 个主题已归纳`},
    {k:'rp', i:'▣', t:'复盘报告', b:(D.slots?D.slots.length:0)+' 条结论', p:`Top${actCount} 可执行建议已生成`}];
  $('#cards').innerHTML = cards.map(c=>`
    <button type="button" class="card" data-k="${c.k}" role="tab" aria-pressed="false" aria-label="查看${c.t}">
      <h3><span class="ico">${c.i}</span>${c.t}</h3>
      <div class="big">${c.b}</div>
      <div class="peek">${c.p}</div>
    </button>`).join('');

  const empty = $('#insight-empty');
  const detailEl = $('#drill');
  const state = $('#insight-state');
  if(state){
    state.setAttribute('role', 'button');
    state.setAttribute('tabindex', '0');
    state.setAttribute('aria-label', '清空洞察选择');
  }
  const syncInsightUI = () => {
    const active = activeInsightKey;
    $$('.card').forEach(card => {
      const on = card.dataset.k === active;
      card.classList.toggle('on', on);
      card.setAttribute('aria-pressed', String(on));
    });
    const insightPanel = $('#result .insight-panel');
    if(active){
      empty?.classList.add('is-hidden');
      detailEl?.classList.remove('hide');
      state?.classList.add('is-active');
      insightPanel?.classList.add('is-active');
      if(state) state.innerHTML = '<span class="state-dot"></span><span>正在查看 ' + ({dm:'弹幕反馈',pk:'高能时刻',cm:'评论总结',rp:'复盘报告'}[active] || '视角') + ' · 点击收起</span>';
    }else{
      empty?.classList.remove('is-hidden');
      detailEl?.classList.add('hide');
      if(state){ state.classList.remove('is-active'); state.innerHTML = '<span class="state-dot"></span><span>未选择视角</span>'; }
      insightPanel?.classList.remove('is-active');
    }
  };

  const openInsight = (key) => {
    if(activeInsightKey === key){
      activeInsightKey = null;
      if(detailEl) detailEl.innerHTML = '';
      syncInsightUI();
      return;
    }
    activeInsightKey = key;
    detailEl?.classList.remove('hide');
    window.drill(key);
    syncInsightUI();
  };

  $$('.card').forEach(card=>{
    card.onclick=()=>openInsight(card.dataset.k);
    card.onkeydown=e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); openInsight(card.dataset.k); } };
  });
  activeInsightKey = null;
  syncInsightUI();

  if(state){
    const resetInsight = () => {
      if(!activeInsightKey) return;
      activeInsightKey = null;
      if(detailEl) detailEl.innerHTML = '';
      syncInsightUI();
    };
    state.onclick = resetInsight;
    state.onkeydown = e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); resetInsight(); } };
  }

  const gotoRef = (kind, idx) => {
    // 本次不生成独立提问分类，所以正常只会跳 dm / pk / cm。
    const cardKind = ['dm','pk','cm'].includes(kind) ? kind : 'rp';
    if(activeInsightKey !== cardKind){
      openInsight(cardKind);
    }else{
      detailEl?.classList.remove('hide');
      if(detailEl && !detailEl.innerHTML.trim()) window.drill(cardKind);
      syncInsightUI();
    }

    setTimeout(()=>{
      const target = detailEl?.querySelector(`[data-anchor="${kind}-${idx}"]`)
        || detailEl?.querySelector(`[data-i="${idx}"]`);
      if(!target) return;
      if(target.classList.contains('theme')) target.classList.add('open');
      if(target.matches('.dm-band-row')) target.click();
      target.scrollIntoView({behavior:'smooth', block:'center'});
      target.classList.remove('hl');
      void target.offsetWidth;   // 强制重排，让动画能重复触发
      target.classList.add('hl');
      setTimeout(()=>target.classList.remove('hl'), 1700);
    }, 120);
  };

  $('#slots').innerHTML = (D.slots||[]).map((s, idx)=>{
    const refs = (s.refs||[]).map(r=>
      `<span class="reflink" role="button" tabindex="0" data-rk="${escapeHtml(r.k)}" data-ri="${Number(r.i)||0}">▸ ${escapeHtml(r.label)}</span>`
    ).join('');
    return `<div class="slot" data-idx="${idx}"><h4>${escapeHtml(s.h)}</h4><p>${escapeHtml(s.p)}</p>`
      + (refs ? `<div class="refs">${refs}</div>`
              : `<div class="slot-empty">${escapeHtml(s.r||'无匹配项')}</div>`)
      + `</div>`;
  }).join('');
  $$('#slots .reflink').forEach(el=>{
    const fire = () => gotoRef(el.dataset.rk, parseInt(el.dataset.ri, 10));
    el.onclick = fire;
    el.onkeydown = e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); fire(); } };
  });
  $('#acts').innerHTML = (D.acts||[]).map(a=>
    `<div class="act"><div><div>${a.t}</div><div class="src">依据：${a.s}</div></div></div>`).join('');
  renderWordClouds(D);

  R.scrollIntoView({behavior:'smooth'});
}
