//! Opt-in real-session probe; not linked into the application binary.
use quietclerk_app::login_service;

fn main() {
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .expect("HOME is required");
    let result = match std::env::args().nth(1).as_deref() {
        Some("register") => login_service::register(&home),
        Some("unregister") => login_service::unregister(&home),
        Some("status") => login_service::status(&home),
        _ => Err("expected status, register or unregister".into()),
    };
    match result {
        Ok(state) => println!("{state:?}"),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
