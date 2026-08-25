// Progress panel behaviour.
let progressTimer = null;
let phraseTimer = null;
let progressValue = 0;
let progressTarget = 0;
let activeStatus = '准备接入弹幕宇宙…';

const STAGE_COUNT = 5;
const STAGE_WEIGHT = 100 / STAGE_COUNT;
let currentStage = 0;
let currentStagePct = 0;
const STAGE_EMOJI = ['📡','🧼','🧩','🧠','📄'];
const CUTE_PHRASES = [
  '小助手正在戴上耳机听大家聊天 ✨',
  '正在把密密麻麻的弹幕揉成小云朵 ☁️',
  '评论区的小情绪正在排队进场 🐣',
  '抓到几只高能片段，先放进收藏篮 🧺',
  '正在给观点贴上温柔的小标签 🏷️',
  '争议点在冒泡泡，马上帮你捞出来 🫧',
  '弹幕小精灵正在搬运关键词 🧚',
  '把观众的「哈哈哈」和「但是」分开放好 😆',
  '正在检查有没有复读机偷偷混进来 🤖',
  '灵感炉火已点燃，报告马上出锅 🍳',
  '请稍等，AI 正在认真眨眼思考 👀',
  '快好了快好了，最后再撒一点清晰度 🌟'
];

function pickCutePhrase(){
  return CUTE_PHRASES[Math.floor(Math.random() * CUTE_PHRASES.length)];
}

function setStatusText(text){
  activeStatus = text || activeStatus;
  const strip = $('#status-strip');
  if(!strip) return;
  strip.classList.remove('roll');
  void strip.offsetWidth;
  strip.textContent = activeStatus;
  strip.classList.add('roll');
}

function setCuteLine(text){
  const el = $('#cute-line');
  if(!el) return;
  el.classList.add('switching');
  setTimeout(()=>{
    el.textContent = text || pickCutePhrase();
    el.classList.remove('switching');
  }, 170);
}

function setProgressVisual(value){
  const pct = Math.max(0, Math.min(100, value));
  const rounded = Math.round(pct);
  const fill = $('#progress-fill');
  const num = $('#progress-num');
  if(fill) fill.style.width = `${pct}%`;
  if(num) num.textContent = `${rounded}%`;
}

function markProgressStage(stage, stagePct = 0){
  $$('.stage').forEach(el=>{
    const k = Number(el.dataset.k);
    const isDone = k < stage || (k === stage && stagePct >= 1);
    const isDoing = k === stage && stagePct < 1;
    el.className = 'stage' + (isDone ? ' done' : isDoing ? ' doing' : '');
  });
}

function normalizeStagePct(value){
  const n = Number(value);
  if(!Number.isFinite(n)) return null;
  // 后端约定 0~1；兼容误传 0~100 的情况。
  return Math.max(0, Math.min(1, n > 1 ? n / 100 : n));
}

function calcGlobalProgress(stage, stagePct){
  const safeStage = Math.max(0, Math.min(STAGE_COUNT - 1, Number(stage) || 0));
  const safePct = Math.max(0, Math.min(1, Number(stagePct) || 0));
  return safeStage * STAGE_WEIGHT + safePct * STAGE_WEIGHT;
}

function resetProgressUI(){
  clearInterval(progressTimer);
  clearInterval(phraseTimer);
  progressValue = 0;
  progressTarget = 0;
  currentStage = 0;
  currentStagePct = 0;
  $('#prog')?.classList.remove('error');
  $('#progress-fill')?.classList.remove('error');
  setProgressVisual(0);
  setStatusText('✨ 准备接入弹幕宇宙，初始化分析引擎…');
  setCuteLine('小助手正在戴上耳机听大家聊天 ✨');
  $$('.stage').forEach(s=>s.className='stage');

  progressTimer = setInterval(()=>{
    if(progressValue < progressTarget){
      progressValue += Math.max(.12, (progressTarget - progressValue) * .12);
      if(progressValue > progressTarget) progressValue = progressTarget;
    }
    setProgressVisual(Math.min(progressValue, 99));
  }, 80);

  phraseTimer = setInterval(()=>{
    setCuteLine(`${STAGE_EMOJI[Math.min(4, Math.max(0, currentStage))]} ${pickCutePhrase()}`);
  }, 2500);
}

function updateProgressFromEvent(d){
  const stage = Math.max(0, Math.min(STAGE_COUNT - 1, Number(d.stage || 0)));
  const parsedPct = normalizeStagePct(d.pct);
  const nextStagePct = parsedPct == null
    ? (stage > currentStage ? 0 : Math.min(currentStagePct + 0.16, 0.92))
    : parsedPct;
  const globalTarget = calcGlobalProgress(stage, nextStagePct);

  currentStage = stage;
  currentStagePct = nextStagePct;
  progressTarget = Math.max(progressTarget, globalTarget);

  const emoji = STAGE_EMOJI[stage] || '✨';
  const extra = d.extra ? ` · ${d.extra}` : '';
  markProgressStage(stage, nextStagePct);
  setStatusText(`${emoji} ${d.msg || '正在分析'}${extra}`);
  setCuteLine(`${emoji} ${pickCutePhrase()}`);
}

function finishProgressUI(){
  clearInterval(progressTimer);
  clearInterval(phraseTimer);
  progressValue = 100;
  progressTarget = 100;
  setProgressVisual(100);
  setStatusText('🎉 复盘报告生成完成，正在整理漂亮版结果…');
  setCuteLine('报告已经热乎乎出炉啦，准备展开给你看 ✨');
  $$('.stage').forEach(s=>s.className='stage done');
}

function showProgressError(msg){
  clearInterval(progressTimer);
  clearInterval(phraseTimer);
  $('#prog')?.classList.add('error');
  $('#progress-fill')?.classList.add('error');
  setStatusText(`❌ ${msg || '连接中断，请稍后重试'}`);
  setCuteLine('小助手摔了一跤，但问题已经被标出来了 🩹');
  $$('.stage.doing').forEach(s=>s.classList.add('error'));
}
