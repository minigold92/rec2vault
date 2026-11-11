'use strict';
(async () => {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const token = fragment.get('bootstrap');
  history.replaceState(null, '', location.pathname + location.search);
  const target = document.getElementById('bootstrap-status');
  try {
    if (token) {
      const response = await fetch('/api/session', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})
      });
      if (!response.ok) throw new Error('bootstrap');
      await response.text();  // finish the exchange before leaving the page, so nothing is aborted
      sessionStorage.setItem('qc.csrf', response.headers.get('X-CSRF-Token'));
    } else {
      const response = await fetch('/api/session', {credentials: 'same-origin'});
      if (!response.ok) throw new Error('session');
      sessionStorage.setItem('qc.csrf', (await response.json()).csrf_token);
    }
    if (target) target.textContent = 'QuietClerk: authenticated';
    window.dispatchEvent(new Event('quietclerk:authenticated'));
    location.replace(fragment.get('next') === 'setup' ? '/setup/1' : '/home');
  } catch (_) {
    if (target) target.textContent = 'Run quietclerk open to sign in.';
  }
})();
