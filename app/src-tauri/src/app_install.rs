//! App installation policy; the probe and the UI call exactly this entrypoint.
use crate::{bootstrap, login_service};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Write},
    os::unix::{
        fs::{MetadataExt, OpenOptionsExt},
        process::CommandExt,
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::atomic::{AtomicI32, Ordering},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
pub const MANIFEST_HASH: &str = match option_env!("QUIETCLERK_MANIFEST_SHA256") {
    Some(value) => value,
    None => "",
};
#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    Missing,
    Cli,
    Ready,
    Setup,
}
pub fn safe_path(path: &Path) -> Result<(), String> {
    for parent in path.ancestors() {
        if let Ok(info) = fs::symlink_metadata(parent) {
            if info.file_type().is_symlink() {
                return Err("설치 경로의 심볼릭 링크를 제거하세요. / Remove symbolic links from installation paths.".into());
            }
        }
    }
    Ok(())
}
fn private_file(path: &Path) -> Result<File, String> {
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|e| e.to_string())?;
    let info = file.metadata().map_err(|e| e.to_string())?;
    bootstrap::validate_metadata(info.uid(), info.mode(), info.is_file(), unsafe {
        libc::getuid()
    })?;
    Ok(file)
}
fn lock(support: &Path) -> Result<File, String> {
    safe_path(support)?;
    fs::create_dir_all(support).map_err(|e| e.to_string())?;
    let file = private_file(&support.join("app-install.lock"))?;
    use std::os::fd::AsRawFd;
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err("다른 앱에서 설치 중입니다. 잠시 후 다시 시도하세요. / Another app is installing; retry shortly.".into());
    }
    // Surviving installer children retain exclusion if the UI is force-killed.
    if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_SETFD, 0) } == -1 {
        return Err("cannot inherit installation lock".into());
    }
    Ok(file)
}
#[derive(Deserialize)]
struct Manifest {
    schema: u32,
    wheel: String,
    wheel_sha256: String,
    requirements_sha256: String,
    inputs_sha256: String,
    bootstrap_sha256: String,
}
fn verify(resources: &Path, expected: &str) -> Result<PathBuf, String> {
    let bytes = fs::read(resources.join("manifest.json")).map_err(|e| e.to_string())?;
    if expected.is_empty() || format!("{:x}", Sha256::digest(&bytes)) != expected {
        return Err("앱 리소스가 손상되었습니다. 앱을 다시 설치하세요. / App resources are damaged; reinstall the app.".into());
    }
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if manifest.schema != 1
        || Path::new(&manifest.wheel)
            .file_name()
            .and_then(|s| s.to_str())
            != Some(&manifest.wheel)
        || !manifest.wheel.ends_with(".whl")
    {
        return Err("invalid bundled engine manifest".into());
    }
    for (name, hash) in [
        (&*manifest.wheel, &manifest.wheel_sha256),
        ("requirements.txt", &manifest.requirements_sha256),
        ("build-inputs.json", &manifest.inputs_sha256),
        ("bootstrap-requirements.txt", &manifest.bootstrap_sha256),
    ] {
        let data = fs::read(resources.join(name)).map_err(|e| e.to_string())?;
        if format!("{:x}", Sha256::digest(data)) != *hash {
            return Err("앱 리소스 해시 불일치 / App resource checksum mismatch".into());
        }
    }
    Ok(resources.join(manifest.wheel))
}
fn execute(
    command: &mut Command,
    log: &mut File,
    progress: &impl Fn(&str, &str),
    pid: &AtomicI32,
) -> Result<(), String> {
    command
        .stdout(Stdio::piped())
        .stderr(log.try_clone().map_err(|e| e.to_string())?);
    unsafe {
        command.pre_exec(|| {
            if libc::setpgid(0, 0) == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    pid.store(child.id() as i32, Ordering::SeqCst);
    let mut error = None;
    for line in BufReader::new(child.stdout.take().unwrap()).lines() {
        let line = line.map_err(|e| e.to_string())?;
        writeln!(log, "{line}").map_err(|e| e.to_string())?;
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
            if let (Some(ko), Some(en)) = (value["ko"].as_str(), value["en"].as_str()) {
                progress(ko, en);
            }
            if let Some(reason) = value["error"].as_str() {
                error = Some(reason.to_string());
            }
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    pid.store(0, Ordering::SeqCst);
    if status.success() {
        Ok(())
    } else {
        Err(error.unwrap_or_else(|| "설치에 실패했습니다. app-install.log를 확인하고 다시 시도하세요. / Installation failed; check app-install.log and retry.".into()))
    }
}
fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|e| e.to_string())
}
pub fn authenticated(home: &Path) -> Result<(), String> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs_f64();
    let data = bootstrap::read_bootstrap(
        &login_service::support(home).join("bootstrap.json"),
        now,
        unsafe { libc::getuid() },
    )?;
    let base = format!("http://127.0.0.1:{}", data.port);
    let client = client()?;
    let response = client
        .post(format!("{base}/api/session"))
        .header("Origin", &base)
        .json(&serde_json::json!({"token":data.token}))
        .send()
        .and_then(|r| r.error_for_status())
        .map_err(|_| "엔진 인증 실패 / Engine authentication failed")?;
    let cookie = response
        .headers()
        .get("set-cookie")
        .and_then(|s| s.to_str().ok())
        .and_then(|s| s.split(';').next())
        .ok_or("missing session cookie")?
        .to_string();
    let csrf = response
        .headers()
        .get("x-csrf-token")
        .ok_or("missing CSRF header")?
        .clone();
    let status = client
        .get(format!("{base}/api/status"))
        .header("Cookie", &cookie)
        .send()
        .and_then(|r| r.error_for_status())
        .and_then(|r| r.json::<serde_json::Value>());
    client
        .post(format!("{base}/api/logout"))
        .header("Origin", &base)
        .header("Cookie", cookie)
        .header("X-CSRF-Token", csrf)
        .json(&serde_json::json!({}))
        .send()
        .and_then(|r| r.error_for_status())
        .map_err(|_| "engine logout failed")?;
    status
        .map(|_| ())
        .map_err(|_| "엔진 상태 인증 실패 / Engine status authentication failed".into())
}
fn preflight(home: &Path) -> Result<(), String> {
    if std::env::consts::OS != "macos" || std::env::consts::ARCH != "aarch64" {
        return Err("Apple Silicon Mac이 필요합니다. / An Apple Silicon Mac is required.".into());
    }
    let version = Command::new("/usr/bin/sw_vers")
        .arg("-productVersion")
        .output()
        .map_err(|e| e.to_string())?;
    if String::from_utf8_lossy(&version.stdout)
        .split('.')
        .next()
        .and_then(|s| s.parse::<u32>().ok())
        .unwrap_or(0)
        < 14
    {
        return Err("macOS 14 이상이 필요합니다. / macOS 14 or later is required.".into());
    }
    use std::os::unix::ffi::OsStrExt;
    let path = std::ffi::CString::new(home.as_os_str().as_bytes()).map_err(|e| e.to_string())?;
    let mut info = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::statvfs(path.as_ptr(), info.as_mut_ptr()) } != 0 {
        return Err("cannot read available disk space".into());
    }
    let info = unsafe { info.assume_init() };
    if u128::from(info.f_bavail).saturating_mul(u128::from(info.f_frsize)) < 8_000_000_000 {
        return Err("엔진 약 2GB + 모델 약 6GB, 여유 8GB가 필요합니다. / Free 8GB for the engine (~2GB) and models (~6GB).".into());
    }
    let client = client()?;
    for url in ["https://pypi.org/simple/", "https://huggingface.co/"] {
        client.head(url).send().and_then(|r| r.error_for_status()).map_err(|_| "인터넷 연결을 확인하고 다시 시도하세요. / Check your internet connection and retry.")?;
    }
    Ok(())
}
/// Called off the UI thread. No user-controlled paths are accepted by IPC.
pub fn perform_install(
    home: &Path,
    resources: &Path,
    tools: &Path,
    expected: &str,
    consent: bool,
    progress: impl Fn(&str, &str),
    pid: &AtomicI32,
) -> Result<Outcome, String> {
    let support = login_service::support(home);
    safe_path(&support)?;
    safe_path(&home.join("QuietClerk"))?;
    let service = login_service::status(home)?;
    if service.manager.as_deref() == Some("cli") {
        authenticated(home)?;
        return Ok(Outcome::Cli);
    }
    if service.manager.as_deref() == Some("app") && !support.join("app-transaction.json").exists() {
        if !service.login_enabled {
            return Err(
                "백그라운드 서비스를 다시 켜세요. / Enable the background service before retrying."
                    .into(),
            );
        }
        let identity_path = support.join("app-engine.json");
        if identity_path.exists() {
            let file = private_file(&identity_path)?;
            let identity: serde_json::Value =
                serde_json::from_reader(file).map_err(|e| e.to_string())?;
            let manifest: serde_json::Value = serde_json::from_slice(
                &fs::read(resources.join("manifest.json")).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            if [
                "version",
                "wheel_sha256",
                "requirements_sha256",
                "inputs_sha256",
            ]
            .iter()
            .all(|key| identity[*key].is_string() && identity[*key] == manifest[*key])
            {
                verify(resources, expected)?;
                login_service::register(home)?;
                authenticated(home)?;
                return Ok(if support.join("app-open-setup").exists() {
                    Outcome::Setup
                } else {
                    Outcome::Ready
                });
            }
        }
    }
    if service.manager.is_none() && !consent {
        return Ok(Outcome::Missing);
    }
    let _lock = lock(&support)?;
    let mut log = private_file(&support.join("app-install.log"))?;
    log.set_len(0).map_err(|e| e.to_string())?;
    let wheel = verify(resources, expected).inspect_err(|error| {
        let _ = writeln!(log, "{error}");
    })?;
    progress(
        "Mac·디스크·네트워크 점검 중",
        "Checking Mac, disk space and network",
    );
    preflight(home).inspect_err(|error| {
        let _ = writeln!(log, "{error}");
    })?;
    progress("Python 3.12 준비 중", "Preparing Python 3.12");
    let bootstrap = support.join("app-bootstrap");
    safe_path(&bootstrap)?;
    execute(
        Command::new(tools.join("uv"))
            .args(["venv", "--clear", "--managed-python", "--python", "3.12"])
            .arg(&bootstrap),
        &mut log,
        &progress,
        pid,
    )?;
    execute(
        Command::new(tools.join("uv"))
            .args(["pip", "install", "--no-deps", "--python"])
            .arg(bootstrap.join("bin/python"))
            .arg(wheel),
        &mut log,
        &progress,
        pid,
    )?;
    execute(
        Command::new(tools.join("uv"))
            .args([
                "pip",
                "install",
                "--no-deps",
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--python",
            ])
            .arg(bootstrap.join("bin/python"))
            .arg("-r")
            .arg(resources.join("bootstrap-requirements.txt")),
        &mut log,
        &progress,
        pid,
    )?;
    let mut command = Command::new(bootstrap.join("bin/python"));
    command
        .args(["-I", "-u", "-m", "quietclerk.app_install", "--resources"])
        .arg(resources)
        .arg("--tools")
        .arg(tools);
    if consent {
        command.arg("--consent");
    }
    execute(&mut command, &mut log, &progress, pid)?;
    authenticated(home)?;
    Ok(if support.join("app-open-setup").exists() {
        Outcome::Setup
    } else {
        Outcome::Ready
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn concurrent_installs_and_symlinks_are_rejected() {
        let temp = tempfile::tempdir().unwrap();
        let canonical = temp.path().canonicalize().unwrap();
        let support = canonical.join("support");
        let _first = lock(&support).unwrap();
        assert!(lock(&support).is_err());
        std::os::unix::fs::symlink(&support, canonical.join("link")).unwrap();
        assert!(safe_path(&canonical.join("link/child")).is_err());
    }
    #[test]
    fn resources_require_compiled_manifest_and_matching_bytes() {
        let temp = tempfile::tempdir().unwrap();
        let resources = temp.path();
        let mut manifest = serde_json::json!({"schema":1,"wheel":"engine.whl"});
        for (name, field) in [
            ("engine.whl", "wheel_sha256"),
            ("requirements.txt", "requirements_sha256"),
            ("build-inputs.json", "inputs_sha256"),
            ("bootstrap-requirements.txt", "bootstrap_sha256"),
        ] {
            fs::write(resources.join(name), name).unwrap();
            manifest[field] = format!("{:x}", Sha256::digest(name.as_bytes())).into();
        }
        let bytes = serde_json::to_vec(&manifest).unwrap();
        fs::write(resources.join("manifest.json"), &bytes).unwrap();
        let expected = format!("{:x}", Sha256::digest(&bytes));
        assert!(verify(resources, &expected).is_ok());
        assert!(verify(resources, "").is_err());
        for file in ["engine.whl", "requirements.txt"] {
            let original = fs::read(resources.join(file)).unwrap();
            fs::write(resources.join(file), b"damaged").unwrap();
            assert!(verify(resources, &expected).is_err());
            fs::write(resources.join(file), original).unwrap();
        }
    }
}
