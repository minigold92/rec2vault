#[derive(Clone, Copy)]
pub enum CheckResult {
    Available,
    Current,
    Failed,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Notice {
    AskToInstall,
    UpToDate,
    Failed,
    Silent,
}

pub fn notice(manual: bool, result: CheckResult) -> Notice {
    match (manual, result) {
        (_, CheckResult::Available) => Notice::AskToInstall,
        (true, CheckResult::Current) => Notice::UpToDate,
        (true, CheckResult::Failed) => Notice::Failed,
        (false, CheckResult::Current | CheckResult::Failed) => Notice::Silent,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn automatic_checks_only_announce_available_updates() {
        assert_eq!(notice(false, CheckResult::Available), Notice::AskToInstall);
        assert_eq!(notice(false, CheckResult::Current), Notice::Silent);
        assert_eq!(notice(false, CheckResult::Failed), Notice::Silent);
    }

    #[test]
    fn explicit_checks_report_every_outcome() {
        assert_eq!(notice(true, CheckResult::Available), Notice::AskToInstall);
        assert_eq!(notice(true, CheckResult::Current), Notice::UpToDate);
        assert_eq!(notice(true, CheckResult::Failed), Notice::Failed);
    }
}
