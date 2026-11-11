// QuietClerk UI — small progressive enhancement only. Pages are readable without it.
// Product parts: language switch, audio segment playback, copy, offline disabling.
// Prototype-only parts (marked PROTO): ?state= switcher, ?shot= capture mode.
(() => {
  const root = document.documentElement;
  const q = new URLSearchParams(location.search);

  // --- language (product: settings key ui.language, applied immediately) ---
  const setLang = (lang) => {
    root.lang = lang;
    try { localStorage.setItem('qc-lang', lang); } catch (_) {}
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const v = el.getAttribute('data-' + lang);
      if (v === null) return;
      if (el.dataset.i18n === 'text') el.textContent = v; // <option> cannot hold both languages
      else el.setAttribute(el.dataset.i18n, v);
    });
    const t = document.querySelector('meta[name="qc-title-' + lang + '"]');
    if (t) document.title = t.content;
    document.querySelectorAll('.langsw button').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));
  };
  let stored = null;
  try { stored = localStorage.getItem('qc-lang'); } catch (_) {}
  const sys = (navigator.language || 'ko').toLowerCase().startsWith('ko') ? 'ko' : 'en';
  setLang(q.get('lang') || stored || sys);
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.langsw button');
    if (b) setLang(b.dataset.lang);
  });

  // --- PROTO: state switcher. In templates each [data-when] block becomes a server-side branch. ---
  const state = q.get('state') || 'normal';
  document.body.dataset.state = state;
  document.querySelectorAll('[data-when]').forEach((el) => {
    el.hidden = !el.dataset.when.split(' ').includes(state);
  });
  if (q.get('shot')) root.classList.add('shot');
  document.querySelectorAll('.proto a[data-state]').forEach((a) => {
    if (a.dataset.state === state) a.setAttribute('aria-current', 'true');
  });

  // --- offline: engine unreachable → disable anything that needs it ---
  if (state === 'offline') {
    document.querySelectorAll('.needs-engine').forEach((el) => {
      if ('disabled' in el) el.disabled = true;
      el.setAttribute('aria-disabled', 'true');
    });
  }
  document.addEventListener('click', (e) => {
    if (e.target.closest('a[aria-disabled="true"]')) e.preventDefault();
  }, true);

  // --- evidence time → play that audio segment ---
  const audio = document.querySelector('audio[data-player]');
  if (audio) {
    let stopAt = null;
    const turns = [...document.querySelectorAll('.tx li[data-start]')];
    document.addEventListener('click', (e) => {
      const b = e.target.closest('[data-seek]');
      if (!b) return;
      const [s, end] = b.dataset.seek.split('-').map(Number);
      document.querySelectorAll('.ts.playing').forEach((x) => x.classList.remove('playing'));
      b.classList.add('playing');
      stopAt = end;
      audio.currentTime = s;
      audio.play().catch(() => {});
    });
    audio.addEventListener('timeupdate', () => {
      const t = audio.currentTime;
      if (stopAt !== null && t >= stopAt) { audio.pause(); stopAt = null; }
      turns.forEach((li) => li.classList.toggle('on', t >= +li.dataset.start && t < +li.dataset.end));
    });
    audio.addEventListener('pause', () => {
      document.querySelectorAll('.ts.playing').forEach((x) => x.classList.remove('playing'));
    });
  }

  // --- copy buttons ---
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    const src = document.getElementById(b.dataset.copy);
    if (src && navigator.clipboard) navigator.clipboard.writeText(src.textContent.trim()).catch(() => {});
    const live = document.getElementById('live');
    if (live) live.textContent = root.lang === 'ko' ? '복사했어요' : 'Copied';
  });
})();
