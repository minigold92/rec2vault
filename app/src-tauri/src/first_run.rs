use quietclerk_app::{app_install, bootstrap};
use serde::Serialize;
use std::sync::{
    atomic::{AtomicBool, AtomicI32, Ordering},
    Mutex,
};
use std::time::Instant;
use tauri::Manager;

#[derive(Clone, Serialize)]
pub struct Progress {
    pub state: String,
    pub ko: String,
    pub en: String,
    pub elapsed: u64,
}
pub struct FirstRun {
    progress: Mutex<Progress>,
    started: Mutex<Instant>,
    busy: AtomicBool,
    pub child: AtomicI32,
    pub ready: AtomicBool,
    pub setup: AtomicBool,
}
impl Default for FirstRun {
    fn default() -> Self {
        Self {
            progress: Mutex::new(Progress {
                state: "checking".into(),
                ko: "엔진 확인 중".into(),
                en: "Checking engine".into(),
                elapsed: 0,
            }),
            started: Mutex::new(Instant::now()),
            busy: AtomicBool::new(false),
            child: AtomicI32::new(0),
            ready: AtomicBool::new(false),
            setup: AtomicBool::new(false),
        }
    }
}
fn set(app: &tauri::AppHandle, state: &str, ko: &str, en: &str) {
    *app.state::<FirstRun>().progress.lock().unwrap() = Progress {
        state: state.into(),
        ko: ko.into(),
        en: en.into(),
        elapsed: 0,
    };
    let shell = app.state::<crate::Shell>();
    let label = match state {
        "cli" => crate::l(shell.korean, "CLI 설치 사용 중", "Using CLI installation"),
        "ready" => crate::l(shell.korean, "엔진 실행 중", "Engine running"),
        "missing" => crate::l(shell.korean, "엔진 설치 안 됨", "Engine not installed"),
        _ => crate::l(shell.korean, "엔진 멈춤", "Engine stopped"),
    };
    let _ = shell.engine_status.set_text(label);
    let _ = shell
        .install_item
        .set_enabled(state == "missing" || state == "error");
}
fn trusted(caller: &tauri::WebviewWindow) -> Result<(), String> {
    if bootstrap::allowed_installation_caller(
        caller.label(),
        &caller.url().map_err(|e| e.to_string())?,
    ) {
        return Ok(());
    }
    Err("installation IPC is restricted to the bundled page".into())
}
#[tauri::command]
pub fn installation_status(
    caller: tauri::WebviewWindow,
    app: tauri::AppHandle,
) -> Result<Progress, String> {
    trusted(&caller)?;
    let controller = app.state::<FirstRun>();
    let mut result = controller.progress.lock().unwrap().clone();
    result.elapsed = controller.started.lock().unwrap().elapsed().as_secs();
    Ok(result)
}
#[tauri::command]
pub fn install_engine(caller: tauri::WebviewWindow, app: tauri::AppHandle) -> Result<(), String> {
    trusted(&caller)?;
    start(&app, true);
    Ok(())
}
pub fn start(app: &tauri::AppHandle, consent: bool) {
    let controller = app.state::<FirstRun>();
    if controller.busy.swap(true, Ordering::SeqCst) {
        return;
    }
    *controller.started.lock().unwrap() = Instant::now();
    controller.ready.store(false, Ordering::SeqCst);
    let app = app.clone();
    std::thread::spawn(move || {
        let result = (|| {
            let home = app.path().home_dir().map_err(|e| e.to_string())?;
            let resources = app
                .path()
                .resource_dir()
                .map_err(|e| e.to_string())?
                .join("engine");
            let tools = std::env::current_exe()
                .map_err(|e| e.to_string())?
                .parent()
                .ok_or("missing executable directory")?
                .to_path_buf();
            app_install::perform_install(
                &home,
                &resources,
                &tools,
                app_install::MANIFEST_HASH,
                consent,
                |ko, en| set(&app, "working", ko, en),
                &app.state::<FirstRun>().child,
            )
        })();
        match result {
            Ok(app_install::Outcome::Missing) => set(
                &app,
                "missing",
                "엔진 설치가 필요합니다",
                "Install the engine to continue",
            ),
            Ok(outcome) => {
                app.state::<FirstRun>()
                    .setup
                    .store(outcome == app_install::Outcome::Setup, Ordering::SeqCst);
                let cli = outcome == app_install::Outcome::Cli;
                set(
                    &app,
                    if cli { "cli" } else { "ready" },
                    "엔진 실행 중",
                    "Engine running",
                );
                app.state::<FirstRun>().ready.store(true, Ordering::SeqCst);
                if let Err(error) = crate::open_window(&app) {
                    crate::show_error(&app, error);
                }
            }
            Err(error) => set(&app, "error", &error, &error),
        }
        app.state::<FirstRun>().busy.store(false, Ordering::SeqCst);
    });
}
