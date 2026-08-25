// SSE analysis request orchestration.
function run(){
  const bvInput = $('#bv').value.trim();
  if(!bvInput){ alert('请输入BV号'); return; }

  $('#entry').classList.add('hide');
  $('#prog').classList.remove('hide');
  $('#result').classList.add('hide');
  resetProgressUI();

  // 建立 SSE 连接
  const evtSource = new EventSource('/api/analyze/stream?bvid=' + encodeURIComponent(bvInput));

  evtSource.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    updateProgressFromEvent(d);
  });

  evtSource.addEventListener('done', e => {
    evtSource.close();
    DATA = JSON.parse(e.data);
    finishProgressUI();
    setTimeout(() => {
      $('#prog').classList.add('hide');
      render(DATA);
    }, 850);
  });

  evtSource.addEventListener('error', e => {
    evtSource.close();
    let msg = '连接中断，请稍后重试';
    try {
      if(e.data) msg = JSON.parse(e.data).msg || msg;
    } catch(_) {}
    showProgressError(msg);
  });
}
