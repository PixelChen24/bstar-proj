/* ─── 导出 Markdown ────────────────────────────────────── */

function exportMarkdown(){
  if(!DATA){ alert('请先生成报告'); return; }
  const D=DATA, v=D.video, L=[];

  L.push(`# ${v.title} · 观众复盘报告`,'');
  L.push(`- UP主：${v.up}`);
  L.push(`- 播放 ${v.play} ｜ 弹幕 ${v.dm} ｜ 评论 ${v.cm}`);
  if(v.duration) L.push(`- 时长：${fmtDur(v.duration)}`);
  if(v.bvid) L.push(`- 稿件：https://www.bilibili.com/video/${v.bvid}`);
  if(D.meta) L.push(`- 分析耗时 ${D.meta.elapsed||'-'}s ｜ 模型 ${D.meta.model||'-'}`);
  L.push('');

  if((D.slots||[]).length){
    L.push('## 一页复盘结论','');
    D.slots.forEach(s=>L.push(`**${s.h}**`,'',s.p,'',`> ${s.r}`,''));
  }

  if((D.acts||[]).length){
    L.push('## Top 可执行改进建议','');
    D.acts.forEach((a,i)=>L.push(`${i+1}. ${a.t}`,`   - 依据：${a.s}`));
    L.push('');
  }

  if((D.dmThemes||[]).length){
    L.push('## 弹幕反馈','','| 主题 | 次数 | 集中时段 |','|---|---|---|');
    D.dmThemes.forEach(t=>L.push(`| ${t.n} | ${t.c} | ${t.t} |`));
    L.push('');
  }

  if((D.peaks||[]).length){
    L.push('## 高能时刻','');
    D.peaks.forEach(p=>L.push(`- **${p.tm}**（密度 ${p.x}，${p.n} 条弹幕）${p.s?' — '+p.s:''}`));
    L.push('');
  }

  if((D.cmThemes||[]).length){
    L.push('## 评论总结','');
    D.cmThemes.forEach(t=>{
      L.push(`### ${t.n}　${t.c} 条${t.dis?`（争议度 ${t.dis}）`:''}`,'');
      (t.q||[]).forEach(q=>{
        const tags=[q.k==='con'?'反对面':'支持面',...(q.why||[])].join('｜');
        L.push(`> ${q.t}`,`> — ↑${q.l} ↩${q.r}　${tags}`,'');
      });
      if(t.note) L.push(`*${t.note}*`,'');
    });
  }

  const name=`复盘报告_${(v.bvid||'report')}.md`;
  const url=URL.createObjectURL(new Blob([L.join('\n')],{type:'text/markdown;charset=utf-8'}));
  const a=document.createElement('a');
  a.href=url; a.download=name; a.click();
  URL.revokeObjectURL(url);
}
