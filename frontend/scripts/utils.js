// Generic formatting, parsing and escaping helpers.
function clamp(n, min, max){ return Math.max(min, Math.min(max, n)); }
function hashString(str){
  let h = 2166136261;
  for(let i=0;i<str.length;i++){
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function colorForCloud(kind, idx){
  const palettes = kind === 'dm'
    ? [[233,95,136],[245,167,66],[231,129,168],[220,91,129]]
    : [[39,173,194],[87,203,188],[55,152,190],[120,196,206]];
  const c = palettes[idx % palettes.length];
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

/* "mm:ss" -> 秒 */
function hms2sec(tm){
  const p = String(tm||'').split(':').map(Number);
  if(p.length === 3) return (p[0]*3600 + p[1]*60 + p[2]) || 0;
  if(p.length === 2) return (p[0]*60 + p[1]) || 0;
  return 0;
}

/* 秒 -> "mm:ss" / "h:mm:ss" */
function fmtDur(sec){
  sec = Math.round(sec||0);
  const h = Math.floor(sec/3600), m = Math.floor(sec%3600/60), s = sec%60;
  const pad = n => String(n).padStart(2,'0');
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function fmtThemeShare(count, total){
  if(!total) return '0%';
  return Math.round(count / total * 100) + '%';
}

function parseThemeWindow(label, totalDuration){
  const text = String(label || '').replace(/\s+/g, '');
  const duration = Math.max(0, Number(totalDuration) || 0);
  if(!text) return null;

  const matches = [...text.matchAll(/(\d{1,2}:\d{2}(?::\d{2})?)/g)].map(m => hms2sec(m[1]));
  if(matches.length >= 2){
    let start = matches[0], end = matches[1];
    if(end < start) [start, end] = [end, start];
    return { start, end: Math.max(end, start + 1), kind: 'range' };
  }

  if(matches.length === 1){
    const center = matches[0];
    const spread = text.includes('附近') ? 45 : Math.max(30, Math.min(90, Math.round((duration || center) * 0.05)));
    const start = Math.max(0, center - spread / 2);
    const end = duration ? Math.min(duration, center + spread / 2) : center + spread / 2;
    return { start, end: Math.max(end, start + 1), kind: 'single' };
  }

  if(text.includes('全片')){
    return { start: 0, end: duration || 0, kind: 'full' };
  }

  return null;
}

function fmtThemeWindow(win, duration){
  if(!win) return '时段未知';
  if(win.kind === 'full') return duration ? `全片 · ${fmtDur(duration)}` : '全片';
  const start = fmtDur(win.start);
  const end = fmtDur(win.end);
  if((win.end - win.start) < 30) return `${fmtDur((win.start + win.end) / 2)} 附近`;
  return `${start} — ${end}`;
}

function fmtThemeWindowLabel(win, duration){
  return fmtThemeWindow(win, duration);
}

function themePalette(idx){
  const palette = ['#fb7299', '#f28c64', '#f4a340', '#79c7dc', '#73cfac', '#9b8df2'];
  return palette[idx % palette.length];
}

function hexToRgba(hex, alpha){
  const value = String(hex || '').replace('#', '').trim();
  if(!value) return `rgba(251, 114, 153, ${alpha})`;
  const full = value.length === 3 ? value.split('').map(ch => ch + ch).join('') : value.padEnd(6, '0').slice(0, 6);
  const n = Number.parseInt(full, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
