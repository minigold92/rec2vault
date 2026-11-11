const korean = navigator.language.toLowerCase().startsWith('ko');
const L = (ko, en) => korean ? ko : en;
document.documentElement.lang = korean ? 'ko' : 'en';
const element = id => document.getElementById(id);
const invoke = (name) => window.__TAURI_INTERNALS__.invoke(name);
element('intro').textContent = L('터미널이나 Homebrew 없이, 이 Mac에 엔진을 설치합니다.', 'Install the engine on this Mac without Terminal or Homebrew.');
element('space').textContent = L('엔진 약 2GB. 없는 모델만 받습니다(최대 약 6GB). 받을 크기와 작업 여유 2GB를 점검합니다.', 'Engine ~2GB. Downloads only missing model files (up to about 6 GB). We check the download size plus 2 GB working space.');
element('consent').textContent = L('설치하면 로그인할 때 엔진이 시작되고, 앱을 종료해도 계속 실행됩니다. 녹음은 내려받기 서버에 보내지 않습니다.', 'Installation starts the engine at login; it keeps running after you quit the app. Recordings are not sent to download servers.');
element('install').addEventListener('click', async () => {
  element('install').disabled = true;
  try { await invoke('install_engine'); } catch (error) { element('reason').textContent = String(error); }
});
async function refresh() {
  try {
    const progress = await invoke('installation_status');
    const working = ['checking', 'working'].includes(progress.state);
    element('heading').textContent = L('엔진', 'Engine');
    element('reason').textContent = korean ? progress.ko : progress.en;
    element('busy').hidden = !working;
    element('elapsed').textContent = working ? L(`경과 ${progress.elapsed}초 · 남은 시간은 추정하지 않습니다.`, `Elapsed ${progress.elapsed}s · No estimated time remaining.`) : '';
    element('install').hidden = !['missing', 'error'].includes(progress.state);
    element('install').disabled = working;
    element('install').textContent = progress.state === 'error' ? L('다시 시도', 'Retry') : L('동의하고 엔진 설치', 'Agree and install engine');
  } catch (error) {
    element('reason').textContent = L('설치 상태를 읽지 못했습니다. 앱을 다시 열어 주세요.', 'Could not read installation status. Reopen the app.');
  }
  setTimeout(refresh, 500);
}
refresh();
