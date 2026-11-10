// Entry point for every screen (the server renders one fixed HTML shell; body[data-screen] picks the screen).
// Flow: the session cookie came from the bootstrap exchange (/ + /bootstrap.js); here the page asks for
// its CSRF token, opens the live stream, then loads the screen module.
import {openSession, authEvents} from './lib/api.js';
import {connect, live, markAuthLost, refreshStatus} from './lib/live.js';
import {mountShell, setTitle} from './lib/shell.js';

const SCREENS = {
  home: () => import('./screens/home.js'),
  jobs: () => import('./screens/jobs.js'),
  notes: () => import('./screens/notes.js'),
  note: () => import('./screens/note.js'),
  backlog: () => import('./screens/backlog.js'),
  settings: () => import('./screens/settings.js'),
  migrate: () => import('./screens/migrate.js'),
};

async function main() {
  const screen = document.body.dataset.screen || 'home';
  const wizard = /^setup-([1-6])$/.exec(screen);
  const step = wizard ? Number(wizard[1]) : 0;
  const shell = mountShell(wizard ? 'setup' : screen, {wizardStep: step});
  setTitle('QuietClerk', 'QuietClerk');
  authEvents.addEventListener('lost', markAuthLost);
  try {
    await openSession();
  } catch (error) {
    if (error.status === 401) markAuthLost();
    else live.failed = true;
  }
  connect();
  refreshStatus();
  const module = await (wizard ? import('./screens/setup.js') : SCREENS[screen]());
  await module.mount({...shell, step, jobId: document.body.dataset.job});
}

main().catch((error) => {
  console.error(error);
  document.getElementById('app').textContent = 'QuietClerk: ' + error.message;
});
