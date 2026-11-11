use serde::Deserialize;
use std::{
    fs::OpenOptions,
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::Path,
};
use url::Url;

#[derive(Debug, Deserialize)]
pub struct Bootstrap {
    pub port: u16,
    pub token: String,
    pub expires: f64,
}

pub fn validate_metadata(owner: u32, mode: u32, regular: bool, uid: u32) -> Result<(), String> {
    if owner != uid || mode & 0o7777 != 0o600 || !regular {
        return Err("bootstrap file must be owned by this user with mode 0600".into());
    }
    Ok(())
}

pub fn read_bootstrap(path: &Path, now: f64, uid: u32) -> Result<Bootstrap, String> {
    // Check the opened descriptor, not the pathname: matches the Python reader.
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|e| e.to_string())?;
    let info = file.metadata().map_err(|e| e.to_string())?;
    validate_metadata(info.uid(), info.mode(), info.is_file(), uid)?;
    let data: Bootstrap = serde_json::from_reader(file).map_err(|e| e.to_string())?;
    if data.expires <= now || data.port == 0 {
        return Err("bootstrap token expired; wait for the running server".into());
    }
    Ok(data)
}

pub fn engine_url(data: &Bootstrap) -> Result<Url, url::ParseError> {
    Url::parse(&format!(
        "http://127.0.0.1:{}/#bootstrap={}",
        data.port, data.token
    ))
}

pub fn allowed_navigation(candidate: &Url, port: u16) -> bool {
    candidate.scheme() == "http"
        && candidate.host_str() == Some("127.0.0.1")
        && candidate.port_or_known_default() == Some(port)
        && candidate.username().is_empty()
        && candidate.password().is_none()
}

pub fn is_korean(language: &str) -> bool {
    language
        .split(['-', '_'])
        .next()
        .is_some_and(|s| s.eq_ignore_ascii_case("ko"))
}

pub fn allowed_bundled_navigation(candidate: &Url) -> bool {
    candidate.scheme() == "tauri"
        && candidate.host_str() == Some("localhost")
        && matches!(candidate.path(), "" | "/" | "/index.html")
        && candidate.username().is_empty()
        && candidate.password().is_none()
}

pub fn allowed_installation_caller(label: &str, origin: &Url) -> bool {
    label.starts_with("main-") && allowed_bundled_navigation(origin)
}

#[test]
fn installation_ipc_rejects_remote_and_other_windows() {
    for origin in [
        "http://127.0.0.1:8765/",
        "https://example.test/",
        "tauri://localhost/other.html",
    ] {
        assert!(!allowed_installation_caller(
            "main-1",
            &Url::parse(origin).unwrap()
        ));
    }
    let bundled = Url::parse("tauri://localhost/").unwrap();
    assert!(allowed_installation_caller("main-1", &bundled));
    assert!(!allowed_installation_caller("engine", &bundled));
}

#[test]
fn bundled_index_uses_root_url() {
    for target in [
        "tauri://localhost",
        "tauri://localhost/",
        "tauri://localhost/index.html",
    ] {
        assert!(allowed_bundled_navigation(&Url::parse(target).unwrap()));
    }
    for target in [
        "tauri://localhost/other",
        "https://example.com/",
        "http://localhost/",
    ] {
        assert!(!allowed_bundled_navigation(&Url::parse(target).unwrap()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        os::unix::fs::{symlink, PermissionsExt},
    };

    #[test]
    fn ownership_permissions_and_type() {
        assert!(validate_metadata(42, 0o100600, true, 42).is_ok());
        for (owner, mode, regular) in [
            (43, 0o600, true),
            (42, 0o644, true),
            (42, 0o4600, true),
            (42, 0o600, false),
        ] {
            assert!(validate_metadata(owner, mode, regular, 42).is_err());
        }
    }

    #[test]
    fn private_file_and_invalid_payloads() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bootstrap.json");
        let uid = unsafe { libc::getuid() };
        assert!(read_bootstrap(&path, 100., uid).is_err());
        for (text, valid) in [
            (r#"{"port":1234,"token":"private","expires":101}"#, true),
            (r#"{"port":1234,"token":"","expires":101}"#, true),
            (r#"{"port":1234,"token":"private","expires":100}"#, false),
            (r#"{"port":0,"token":"private","expires":101}"#, false),
            (r#"{"port":65536,"token":"private","expires":101}"#, false),
            (r#"{"port":1234,"token":42,"expires":101}"#, false),
            ("not json", false),
        ] {
            fs::write(&path, text).unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
            assert_eq!(read_bootstrap(&path, 100., uid).is_ok(), valid);
        }
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(read_bootstrap(&path, 100., uid).is_err());
        let saved = dir.path().join("saved");
        fs::rename(&path, &saved).unwrap();
        fs::set_permissions(&saved, fs::Permissions::from_mode(0o600)).unwrap();
        symlink(saved, &path).unwrap();
        assert!(read_bootstrap(&path, 100., uid).is_err());
        fs::remove_file(&path).unwrap();
        fs::create_dir(&path).unwrap();
        assert!(read_bootstrap(&path, 100., uid).is_err());
    }

    #[test]
    fn address_and_origin_boundary() {
        let data = Bootstrap {
            port: 1234,
            token: "private".into(),
            expires: 101.,
        };
        assert_eq!(
            engine_url(&data).unwrap().as_str(),
            "http://127.0.0.1:1234/#bootstrap=private"
        );
        assert!(allowed_navigation(&engine_url(&data).unwrap(), 1234));
        assert!(allowed_navigation(
            &Url::parse("http://127.0.0.1:1234/settings").unwrap(),
            1234
        ));
        for target in [
            "http://localhost:1234/",
            "http://127.0.0.1:1235/",
            "https://127.0.0.1:1234/",
            "https://example.com/",
            "http://user@127.0.0.1:1234/",
            "file:///tmp/test",
        ] {
            assert!(!allowed_navigation(&Url::parse(target).unwrap(), 1234));
        }
    }

    #[test]
    fn language_selection() {
        for value in ["ko", "ko-KR", "ko_KR", "KO-kr"] {
            assert!(is_korean(value));
        }
        for value in ["en-KR", "en", "kok", "", "ja-JP"] {
            assert!(!is_korean(value));
        }
    }
}
