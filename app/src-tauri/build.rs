use sha2::{Digest, Sha256};

fn main() {
    let path = std::path::Path::new("engine/manifest.json");
    println!("cargo:rerun-if-changed={}", path.display());
    if let Ok(bytes) = std::fs::read(path) {
        println!(
            "cargo:rustc-env=QUIETCLERK_MANIFEST_SHA256={:x}",
            Sha256::digest(bytes)
        );
    }
    tauri_build::build()
}
