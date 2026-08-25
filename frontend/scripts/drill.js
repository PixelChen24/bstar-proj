// Insight detail router.
function drill(k){
  const D = DATA;
  const Dr = $('#drill');
  if(k==='dm'){
    renderDmDrill(D.dmThemes || [], D.peaks || [], (D.video && D.video.duration) || 0);
  }
  else if(k==='pk'){
    // 用真实视频时长定位峰值；缺失时退回按最大峰值时间点估算
    const peaks = D.peaks || [];
    const maxSec = peaks.reduce((m,p)=>Math.max(m, hms2sec(p.tm)), 0);
    const totalDur = (D.video && D.video.duration) || Math.max(maxSec * 1.2, 60);

    const cols=Array.from({length:80},(_,i)=>{
      let h = 8;
      for(const p of peaks){
        const idx = Math.floor(hms2sec(p.tm) / totalDur * 80);
        if(Math.abs(i - idx) <= 1) h = Math.min(58, parseFloat(p.x) * 8);
      }
      const hot = h > 20;
      return `<div class="col ${hot?'hot':''}" style="left:${i*1.25}%;height:${h}px"></div>`;
    }).join('');

    Dr.innerHTML=`<h2>高能时刻</h2>
      <div class="axis">${cols}</div>
      <div class="tiny">横轴为视频进度（全长 ${fmtDur(totalDur)}），粉色为弹幕密度峰值区间</div>
      ${peaks.map((p,i)=>`<div class="peak" data-anchor="pk-${i}" data-i="${i}"><div class="tm">${p.tm}</div>
        <div><div><b>密度 ${p.x}</b>　<span class="muted">该区间 ${p.n} 条弹幕</span></div>
        <div style="margin-top:5px">${p.s||''}</div></div></div>`).join('')}`;
  }
  else if(k==='cm'){
    Dr.innerHTML=`<h2>评论总结 · 点标题展开</h2>
      ${(D.cmThemes||[]).map((t,i)=>`
        <div class="theme ${i===0?'open':''}" data-anchor="cm-${i}" data-i="${i}">
          <div class="theme-hd" onclick="this.parentNode.classList.toggle('open')">
            <span class="arrow">▶</span>
            <span class="nm">${t.n}</span>
            <span class="tiny">${t.c} 条</span>
            <span class="bar"><i style="width:${t.pct||0}%"></i></span>
            ${t.dis?`<span class="badge">争议度 ${t.dis}</span>`:''}
          </div>
          <div class="theme-bd">
            ${(t.q||[]).map(q=>`<div class="quote ${q.k}">${q.t}
              <div class="quote-meta"><span>↑ ${q.l}</span><span>↩ ${q.r}</span>
              <span class="tiny">${q.k==='con'?'反对面':'支持面'}</span>
              ${(q.why||[]).map(w=>`<span class="badge">${w}</span>`).join('')}</div></div>`).join('')}
            ${t.note?`<div class="note">${t.note}</div>`:''}
          </div>
        </div>`).join('')}`;
  }
  else{
    Dr.innerHTML=`<h2>复盘报告</h2>
      <div class="muted">五个固定问题的结论与 Top5 建议见下方「一页复盘结论」。</div>`;
  }
}
