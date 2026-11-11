//! Opt-in real-path entrypoint, never linked into the app. No UI automation.
use quietclerk_app::app_install::{perform_install, MANIFEST_HASH};
use std::{path::PathBuf, sync::atomic::AtomicI32, time::Instant};

fn main() {
    let mut args = std::env::args_os().skip(1);
    let bundle = PathBuf::from(
        args.next()
            .expect("usage: first_run_probe <test.app> --consent"),
    );
    assert_eq!(
        args.next().as_deref(),
        Some(std::ffi::OsStr::new("--consent")),
        "explicit real-install consent is required"
    );
    assert!(args.next().is_none());
    let home = PathBuf::from(std::env::var_os("HOME").expect("HOME"));
    assert!(
        bundle.starts_with(home.join("Applications")),
        "only test bundles in ~/Applications are permitted"
    );
    let started = Instant::now();
    let result = perform_install(
        &home,
        &bundle.join("Contents/Resources/engine"),
        &bundle.join("Contents/MacOS"),
        MANIFEST_HASH,
        true,
        |ko, en| println!("{}s {ko} / {en}", started.elapsed().as_secs()),
        &AtomicI32::new(0),
    );
    match result {
        Ok(outcome) => println!(
            "{outcome:?}; authenticated status; elapsed {:.2}s",
            started.elapsed().as_secs_f64()
        ),
        Err(error) => {
            eprintln!("{error}; elapsed {:.2}s", started.elapsed().as_secs_f64());
            std::process::exit(1);
        }
    }
}
