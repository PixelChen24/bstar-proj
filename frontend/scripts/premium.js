// Premium motion, cursor aura and emoji micro-interactions.
(() => {
  const root = document.documentElement;
  const body = document.body;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const emojis = ['✨','💫','🔥','💬','🧠','🌈','⚡','🪄','📈','🎯','🚀','💎'];
  const sparkleTargets = '.btn, .chip, .card, .reflink, .insight-state, .orbit-card';

  const setPointer = (x, y) => {
    root.style.setProperty('--mx', `${x}px`);
    root.style.setProperty('--my', `${y}px`);
  };

  const spawnSpark = (x, y, label) => {
    if (reducedMotion) return;
    const el = document.createElement('span');
    el.className = 'spark';
    el.textContent = label || emojis[(Math.random() * emojis.length) | 0];
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.setProperty('--dx', `${((Math.random() * 2 - 1) * 140).toFixed(0)}px`);
    el.style.setProperty('--dy', `${(-90 - Math.random() * 120).toFixed(0)}px`);
    document.body.appendChild(el);
    window.setTimeout(() => el.remove(), 850);
  };

  const bindSpark = (e) => {
    const t = e.target.closest(sparkleTargets);
    if (!t) return;
    const r = t.getBoundingClientRect();
    spawnSpark(r.left + r.width * (0.35 + Math.random() * 0.3), r.top + r.height * (0.35 + Math.random() * 0.3), t.textContent?.trim().slice(0, 2) || undefined);
  };

  const revealables = [...document.querySelectorAll('.revealable')];
  const markVisible = el => el.classList.add('is-visible');

  if (!reducedMotion && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          markVisible(entry.target);
          io.unobserve(entry.target);
        }
      }
    }, { threshold: 0.14, rootMargin: '40px 0px -10% 0px' });
    revealables.forEach(el => io.observe(el));
  } else {
    revealables.forEach(markVisible);
  }

  const hoverCard = e => {
    const el = e.target.closest('.panel, .card, .orbit-card, .cloud-card');
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--local-x', `${((e.clientX - r.left) / r.width * 100).toFixed(2)}%`);
    el.style.setProperty('--local-y', `${((e.clientY - r.top) / r.height * 100).toFixed(2)}%`);
  };

  if (!reducedMotion) {
    body.classList.add('motion-ready');
    window.addEventListener('pointermove', e => {
      setPointer(e.clientX, e.clientY);
      hoverCard(e);
    }, { passive: true });
    window.addEventListener('pointerdown', bindSpark, { passive: true });
    window.addEventListener('click', bindSpark, { passive: true });
  } else {
    body.classList.add('motion-ready');
    revealables.forEach(markVisible);
  }

  const formatQuery = () => {
    const v = document.querySelector('#bv');
    if (!v) return;
    v.addEventListener('focus', () => spawnSpark(v.getBoundingClientRect().left + 36, v.getBoundingClientRect().top + 18, '✨'));
  };
  formatQuery();
})();
