//! OS lifecycle writes live in quietclerk.install, never in the app shell.
use crate::bootstrap::validate_metadata;
use serde::Deserialize;
use std::{
    ffi::OsString,
    fs::OpenOptions,
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    process::Command,
};

pub const LABEL: &str = "local.quietclerk.serve";
pub const RECORD_NAME: &str = "engine-installation.json";

#[derive(Debug, Deserialize, PartialEq, Eq)]
pub struct ServiceStatus {
    pub manager: Option<String>,
    pub registered: bool,
    pub login_enabled: bool,
}

#[derive(Debug, Deserialize)]
struct Installation {
    schema: u32,
    manager: String,
    label: String,
    python: PathBuf,
    support: PathBuf,
}

impl Installation {
    fn validate(&self, expected_support: &Path) -> Result<(), String> {
        if self.schema != 1
            || self.manager != "app"
            || self.label != LABEL
            || !self.python.is_absolute()
            || self.support != expected_support
        {
            return Err("invalid app installation record".into());
        }
        Ok(())
    }

    fn read(path: &Path) -> Result<Self, String> {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path)
            .map_err(|e| e.to_string())?;
        let info = file.metadata().map_err(|e| e.to_string())?;
        validate_metadata(info.uid(), info.mode(), info.is_file(), unsafe {
            libc::getuid()
        })?;
        serde_json::from_reader(file).map_err(|e| e.to_string())
    }
}

pub fn support(home: &Path) -> PathBuf {
    home.join("Library/Application Support/QuietClerk")
}

pub fn existing_service(plist_exists: bool, registered: bool) -> ServiceStatus {
    ServiceStatus {
        manager: (plist_exists || registered).then(|| "cli".into()),
        registered,
        login_enabled: plist_exists,
    }
}

fn launchd_registered() -> Result<bool, String> {
    let result = Command::new("/bin/launchctl")
        .args([
            "print",
            &format!("gui/{}/{}", unsafe { libc::getuid() }, LABEL),
        ])
        .output()
        .map_err(|e| e.to_string())?;
    if !result.status.success()
        && !String::from_utf8_lossy(&result.stderr).contains("Could not find service")
    {
        return Err("cannot read launchd registration".into());
    }
    Ok(result.status.success())
}

#[derive(Clone, Copy)]
enum Action {
    Status,
    Register,
    Unregister,
}

fn command_args(support: &Path, action: Action) -> Vec<OsString> {
    let action = match action {
        Action::Status => "status",
        Action::Register => "register",
        Action::Unregister => "unregister",
    };
    vec![
        "-m".into(),
        "quietclerk.cli".into(),
        "--support".into(),
        support.into(),
        "login-service".into(),
        action.into(),
    ]
}

fn invoke(home: &Path, action: Action) -> Result<ServiceStatus, String> {
    let support = support(home);
    let path = support.join(RECORD_NAME);
    if !path.exists() {
        return Ok(existing_service(
            home.join("Library/LaunchAgents")
                .join(format!("{LABEL}.plist"))
                .exists(),
            launchd_registered()?,
        ));
    }
    let installation = Installation::read(&path)?;
    installation.validate(&support)?;
    let output = Command::new(installation.python)
        .args(command_args(&support, action))
        .output()
        .map_err(|e| format!("cannot run installed engine: {e}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
}

/// These functions may wait for engine shutdown/startup; call off the UI thread.
pub fn status(home: &Path) -> Result<ServiceStatus, String> {
    invoke(home, Action::Status)
}
pub fn register(home: &Path) -> Result<ServiceStatus, String> {
    invoke(home, Action::Register)
}
pub fn unregister(home: &Path) -> Result<ServiceStatus, String> {
    invoke(home, Action::Unregister)
}

/// Installed engine version for the menu, read from the app-managed venv's package metadata.
/// It never touches bootstrap.json: that token is single-use, and spending it here raced the
/// window opening after an engine update (0.0.5, 2026-11-11). CLI installs return None.
pub fn engine_version(home: &Path) -> Option<String> {
    let support = support(home);
    let installation = Installation::read(&support.join(RECORD_NAME)).ok()?;
    installation.validate(&support).ok()?;
    let lib = installation.python.parent()?.parent()?.join("lib");
    let site = std::fs::read_dir(lib)
        .ok()?
        .flatten()
        .map(|entry| entry.path().join("site-packages"))
        .find(|path| path.is_dir())?;
    version_from_dist_info(
        std::fs::read_dir(site)
            .ok()?
            .flatten()
            .filter_map(|entry| entry.file_name().into_string().ok()),
    )
}

fn version_from_dist_info(names: impl Iterator<Item = String>) -> Option<String> {
    names
        .filter_map(|name| {
            name.strip_prefix("quietclerk-")?
                .strip_suffix(".dist-info")
                .map(str::to_string)
        })
        .find(|version| !version.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cli_presence_never_becomes_a_second_app_service() {
        for (plist, registered) in [(true, true), (true, false), (false, true)] {
            assert_eq!(
                existing_service(plist, registered).manager.as_deref(),
                Some("cli")
            );
        }
        assert_eq!(existing_service(false, false).manager, None);
    }
    #[test]
    fn engine_version_comes_from_the_package_metadata_folder() {
        let names = ["numpy-2.1.0.dist-info", "quietclerk", "quietclerk-0.1.3.dist-info"];
        assert_eq!(
            version_from_dist_info(names.iter().map(|s| s.to_string())).as_deref(),
            Some("0.1.3")
        );
        let none = ["quietclerk", "quietclerk_app-1.0.dist-info"];
        assert_eq!(version_from_dist_info(none.iter().map(|s| s.to_string())), None);
    }
    #[test]
    fn lifecycle_uses_literal_engine_arguments_without_shell() {
        let path = Path::new("/a home/support ; literal");
        let args = command_args(path, Action::Unregister);
        assert_eq!(
            args,
            [
                "-m",
                "quietclerk.cli",
                "--support",
                "/a home/support ; literal",
                "login-service",
                "unregister"
            ]
            .map(OsString::from)
        );
    }
    #[test]
    fn installation_requires_current_schema_and_fixed_support() {
        let mut record = Installation {
            schema: 1,
            manager: "app".into(),
            label: LABEL.into(),
            python: "/venv/python".into(),
            support: "/support".into(),
        };
        assert!(record.validate(Path::new("/support")).is_ok());
        assert!(record.validate(Path::new("/other")).is_err());
        record.python = "relative".into();
        assert!(record.validate(Path::new("/support")).is_err());
        record.python = "/python".into();
        record.schema = 2;
        assert!(record.validate(Path::new("/support")).is_err());
    }
    #[test]
    fn private_record_rejects_symlinks_and_wrong_permissions() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join(RECORD_NAME);
        std::fs::write(&path, r#"{"schema":1,"manager":"app","label":"local.quietclerk.serve","python":"/python","support":"/support"}"#).unwrap();
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o644)).unwrap();
        assert!(Installation::read(&path).is_err());
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        assert!(Installation::read(&path).is_ok());
        let link = dir.path().join("link");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(Installation::read(&link).is_err());
    }
}
