// Page bootstrap and top-level event binding.
$$('.chip').forEach(c=>c.onclick=()=>{
  $('#bv').value='BV1'+['xx411c7mD','aB4y1P7Qk','cD5x1M8Rn'][c.dataset.s];
});
$('#go').onclick=run;
$('#again').onclick=()=>{
  $('#result').classList.add('hide'); $('#entry').classList.remove('hide');
  window.scrollTo({top:0,behavior:'smooth'});
};
$('#export-md').onclick=exportMarkdown;
window.addEventListener('resize', ()=>{
  if(DATA && !$('#result').classList.contains('hide')) renderWordClouds(DATA);
});
