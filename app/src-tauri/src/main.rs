#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use quietclerk_app::bootstrap;
mod first_run;
mod menu_status;
mod update_policy;

use std::{
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder, TrayIconEvent},
    Manager, WebviewUrl, WebviewWindowBuilder,
};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;

struct Shell {
    korean: bool,
    updating: AtomicBool,
    window_id: AtomicU64,
    engine_status: MenuItem<tauri::Wry>,
    install_item: MenuItem<tauri::Wry>,
    refreshing_status: AtomicBool,
}

fn l<'a>(korean: bool, ko: &'a str, en: &'a str) -> &'a str {
    if korean {
        ko
    } else {
        en
    }
}

fn refresh_engine_status(app: &tauri::AppHandle) {
    let shell = app.state::<Shell>();
    if shell.refreshing_status.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        let status = app
            .path()
            .home_dir()
            .ok()
            .and_then(|home| quietclerk_app::app_install::authenticated_status(&home).ok());
        let shell = app.state::<Shell>();
        let label = menu_status::engine_label(shell.korean, status.as_ref());
        let _ = shell.engine_status.set_text(label);
        shell.refreshing_status.store(false, Ordering::SeqCst);
    });
}

fn show_error(app: &tauri::AppHandle, error: impl std::fmt::Display) {
    let ko = app.state::<Shell>().korean;
    app.dialog()
        .message(format!(
            "{}\n\n{error}",
            l(ko, "작업에 실패했습니다.", "The operation failed.")
        ))
        .title("QuietClerk")
        .kind(MessageDialogKind::Error)
        .show(|_| {});
}

fn open_window(app: &tauri::AppHandle) -> tauri::Result<()> {
    // Create before destroying the old view. Reusing its label lets the queued
    // Destroyed event remove the replacement from Tauri's window registry.
    let previous_id = app.state::<Shell>().window_id.load(Ordering::SeqCst);
    let next_id = previous_id + 1;
    let bootstrap = app
        .state::<first_run::FirstRun>()
        .ready
        .load(Ordering::SeqCst)
        .then(|| {
            app.path().home_dir().ok().and_then(|home| {
                let now = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .ok()?
                    .as_secs_f64();
                bootstrap::read_bootstrap(
                    &home.join("Library/Application Support/QuietClerk/bootstrap.json"),
                    now,
                    unsafe { libc::getuid() },
                )
                .ok()
            })
        })
        .flatten();
    let (url, port) = match bootstrap {
        Some(data) => match bootstrap::engine_url(&data) {
            Ok(mut url) => {
                if app
                    .state::<first_run::FirstRun>()
                    .setup
                    .load(Ordering::SeqCst)
                {
                    url.set_fragment(Some(&format!("bootstrap={}&next=setup", data.token)));
                }
                (WebviewUrl::External(url), Some(data.port))
            }
            Err(_) => (WebviewUrl::App("index.html".into()), None),
        },
        None => (WebviewUrl::App("index.html".into()), None),
    };
    let window = WebviewWindowBuilder::new(app, format!("main-{next_id}"), url)
        .title("QuietClerk")
        .inner_size(1000., 760.)
        .on_navigation(move |url| match port {
            Some(port) => bootstrap::allowed_navigation(url, port),
            None => bootstrap::allowed_bundled_navigation(url),
        })
        .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
        .on_page_load(|window, payload| {
            if payload.url().path() == "/setup/1" {
                window
                    .app_handle()
                    .state::<first_run::FirstRun>()
                    .setup
                    .store(false, Ordering::SeqCst);
                if let Ok(home) = window.app_handle().path().home_dir() {
                    let _ = std::fs::remove_file(
                        home.join("Library/Application Support/QuietClerk/app-open-setup"),
                    );
                }
            }
        })
        .build()?;
    window.show()?;
    window.set_focus()?;
    app.state::<Shell>()
        .window_id
        .store(next_id, Ordering::SeqCst);
    if let Some(previous) = app.get_webview_window(&format!("main-{previous_id}")) {
        previous.destroy()?;
    }
    Ok(())
}

fn check_updates(app: &tauri::AppHandle, manual: bool) {
    if app.state::<Shell>().updating.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let ko = app.state::<Shell>().korean;
        let result = async {
            let updater = app.updater()?;
            Ok::<_, Box<dyn std::error::Error + Send + Sync>>(updater.check().await?)
        }
        .await;
        let outcome = match &result {
            Ok(Some(_)) => update_policy::CheckResult::Available,
            Ok(None) => update_policy::CheckResult::Current,
            Err(error) => {
                eprintln!("QuietClerk update check failed: {error}");
                update_policy::CheckResult::Failed
            }
        };
        match update_policy::notice(manual, outcome) {
            update_policy::Notice::AskToInstall => {
                if let Ok(Some(update)) = result {
                    let prompt = format!(
                        "QuietClerk {}\n{}",
                        update.version,
                        l(
                            ko,
                            "새 버전을 설치하고 앱을 다시 시작할까요?",
                            "Install the new version and restart the app?"
                        )
                    );
                    // Native dialogs must not block the main event loop.
                    if app
                        .dialog()
                        .message(prompt)
                        .title("QuietClerk")
                        .buttons(MessageDialogButtons::OkCancel)
                        .blocking_show()
                    {
                        match update.download_and_install(|_, _| {}, || {}).await {
                            Ok(()) => app.restart(),
                            Err(error) => {
                                eprintln!("QuietClerk update installation failed: {error}");
                                app.dialog()
                                    .message(l(
                                        ko,
                                        "업데이트를 설치하지 못했어요. 나중에 다시 시도해 주세요.",
                                        "Couldn't install the update. Please try again later.",
                                    ))
                                    .title("QuietClerk")
                                    .kind(MessageDialogKind::Error)
                                    .show(|_| {});
                            }
                        }
                    }
                }
            }
            update_policy::Notice::UpToDate => {
                app.dialog()
                    .message(l(ko, "최신 버전입니다.", "You’re up to date."))
                    .title("QuietClerk")
                    .show(|_| {});
            }
            update_policy::Notice::Failed => {
                app.dialog().message(l(ko,
                    "업데이트 정보를 가져오지 못했어요. 인터넷 연결을 확인하고 나중에 다시 시도해 주세요.",
                    "Couldn't get update information. Check your connection and try again later."))
                    .title("QuietClerk").kind(MessageDialogKind::Error).show(|_| {});
            }
            update_policy::Notice::Silent => {}
        }
        app.state::<Shell>().updating.store(false, Ordering::SeqCst);
    });
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            first_run::installation_status,
            first_run::install_engine
        ])
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let ko = bootstrap::is_korean(&sys_locale::get_locale().unwrap_or_default());
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            let open = MenuItem::with_id(
                app,
                "open",
                l(ko, "QuietClerk 열기", "Open QuietClerk"),
                true,
                None::<&str>,
            )?;
            let update = MenuItem::with_id(
                app,
                "update",
                l(ko, "업데이트 확인", "Check for updates"),
                true,
                None::<&str>,
            )?;
            let engine_status = MenuItem::with_id(
                app,
                "engine-status",
                l(ko, "엔진 확인 중", "Checking engine"),
                false,
                None::<&str>,
            )?;
            let app_version = MenuItem::with_id(
                app,
                "app-version",
                menu_status::app_label(ko, env!("CARGO_PKG_VERSION")),
                false,
                None::<&str>,
            )?;
            let install_item = MenuItem::with_id(
                app,
                "install",
                l(ko, "엔진 설치", "Install engine"),
                false,
                None::<&str>,
            )?;
            app.manage(Shell {
                korean: ko,
                updating: AtomicBool::new(false),
                window_id: AtomicU64::new(0),
                engine_status: engine_status.clone(),
                install_item: install_item.clone(),
                refreshing_status: AtomicBool::new(false),
            });
            app.manage(first_run::FirstRun::default());
            let quit = MenuItem::with_id(app, "quit", l(ko, "종료", "Quit"), true, None::<&str>)?;
            let menu = Menu::with_items(
                app,
                &[
                    &engine_status,
                    &app_version,
                    &install_item,
                    &open,
                    &update,
                    &quit,
                ],
            )?;
            TrayIconBuilder::new()
                .icon(tauri::image::Image::from_bytes(include_bytes!(
                    "../icons/tray.png"
                ))?)
                .icon_as_template(true)
                .tooltip("QuietClerk")
                .menu(&menu)
                .on_tray_icon_event(|tray, event| {
                    if matches!(event, TrayIconEvent::Click { .. }) {
                        refresh_engine_status(tray.app_handle());
                    }
                })
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => {
                        if let Err(error) = open_window(app) {
                            show_error(app, error);
                        }
                        first_run::start(app, false);
                    }
                    "update" => check_updates(app, true),
                    "install" => {
                        if let Err(error) = open_window(app) {
                            show_error(app, error);
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            open_window(app.handle())?;
            first_run::start(app.handle(), false);
            check_updates(app.handle(), false);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("QuietClerk could not start")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                let pid = app
                    .state::<first_run::FirstRun>()
                    .child
                    .load(Ordering::SeqCst);
                if pid > 0 {
                    unsafe {
                        libc::killpg(pid, libc::SIGTERM);
                    }
                }
            }
            if let tauri::RunEvent::ExitRequested {
                code: None, api, ..
            } = event
            {
                api.prevent_exit();
            }
        });
}
