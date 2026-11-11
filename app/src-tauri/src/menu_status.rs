use serde_json::Value;

pub fn engine_label(korean: bool, status: Option<&Value>) -> String {
    let engine = if korean { "엔진" } else { "Engine" };
    let state = match status {
        None => {
            if korean {
                "멈춤"
            } else {
                "Stopped"
            }
        }
        Some(value) if value["paused"].as_bool() == Some(true) => {
            if korean {
                "일시정지"
            } else {
                "Paused"
            }
        }
        Some(value) if value["current_job"].is_object() => {
            if korean {
                "처리 중"
            } else {
                "Processing"
            }
        }
        Some(_) => {
            if korean {
                "실행 중"
            } else {
                "Running"
            }
        }
    };
    match status
        .and_then(|value| value["engine_version"].as_str())
        .filter(|v| !v.is_empty())
    {
        Some(version) => format!("{engine} {version} · {state}"),
        None => format!("{engine} {state}"),
    }
}

pub fn app_label(korean: bool, version: &str) -> String {
    format!("{} {version}", if korean { "앱" } else { "App" })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn versions_and_states_in_both_languages() {
        let status = json!({"engine_version": "0.1.2", "paused": false, "current_job": null});
        assert_eq!(engine_label(true, Some(&status)), "엔진 0.1.2 · 실행 중");
        assert_eq!(engine_label(false, Some(&status)), "Engine 0.1.2 · Running");
        assert_eq!(app_label(true, "0.0.4"), "앱 0.0.4");
        assert_eq!(app_label(false, "0.0.4"), "App 0.0.4");
        assert_eq!(engine_label(true, None), "엔진 멈춤");
        assert_eq!(engine_label(false, None), "Engine Stopped");
        for version in [Value::Null, json!(""), json!(42)] {
            assert_eq!(
                engine_label(false, Some(&json!({"engine_version": version}))),
                "Engine Running"
            );
        }
        assert_eq!(
            engine_label(true, Some(&json!({"paused": true}))),
            "엔진 일시정지"
        );
        assert_eq!(
            engine_label(false, Some(&json!({"current_job": {}}))),
            "Engine Processing"
        );
    }
}
