// Page bootstrap and top-level event binding.
const chips = $$('.chip');
chips.forEach(c=>c.onclick=()=>{
  $('#bv').value='BV1'+['sZ3v66E5u','tMgP6SE1Y','Ke3C6FEuc'][c.dataset.s];
  chips.forEach(x=>x.classList.toggle('is-picked', x===c));
});
$('#bv').addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); run(); } });
$('#go').onclick=run;
$('#again').onclick=()=>{
  $('#result').classList.add('hide'); $('#entry').classList.remove('hide');
  if(window.hideHotDanmaku) window.hideHotDanmaku();
  window.scrollTo({top:0,behavior:'smooth'});
};
$('#export-md').onclick=exportMarkdown;
window.addEventListener('resize', ()=>{
  if(DATA && !$('#result').classList.contains('hide')){
    renderWordClouds(DATA);
    if(window.refreshHotDanmaku) window.refreshHotDanmaku();
    else if(window.renderHotDanmaku) window.renderHotDanmaku(DATA);
  }
});
