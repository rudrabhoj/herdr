//! Which account a running agent is logged in to, for the agent label.
//!
//! The server reads it for agents whose login lives in a file it can locate
//! from the agent's own environment. pi switches accounts at runtime through
//! its extensions, so its herdr extension reports its own label instead.

use std::path::{Path, PathBuf};

use base64::Engine;

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum AccountSource {
    /// Claude Code's global config, `<CLAUDE_CONFIG_DIR>/.claude.json`, or
    /// `~/.claude.json` when the variable is unset.
    Claude(PathBuf),
    /// codex's `<CODEX_HOME or ~/.codex>/auth.json`.
    Codex(PathBuf),
}

impl AccountSource {
    pub(crate) fn path(&self) -> &Path {
        match self {
            Self::Claude(path) | Self::Codex(path) => path,
        }
    }
}

pub(crate) fn account_source(
    agent: &str,
    environ: &[u8],
    home: Option<&Path>,
) -> Option<AccountSource> {
    let dir_var = |name: &str| {
        environ
            .split(|&byte| byte == 0)
            .find_map(|record| record.strip_prefix(name.as_bytes())?.strip_prefix(b"="))
            .and_then(|value| std::str::from_utf8(value).ok())
            .filter(|value| !value.is_empty())
            .map(PathBuf::from)
    };
    match agent {
        "claude" => Some(AccountSource::Claude(match dir_var("CLAUDE_CONFIG_DIR") {
            Some(dir) => dir.join(".claude.json"),
            None => home?.join(".claude.json"),
        })),
        "codex" => Some(AccountSource::Codex(
            dir_var("CODEX_HOME")
                .or_else(|| Some(home?.join(".codex")))?
                .join("auth.json"),
        )),
        _ => None,
    }
}

/// The account email, or `None` when logged out or unreadable.
pub(crate) fn read_account(source: &AccountSource) -> Option<String> {
    let json: serde_json::Value =
        serde_json::from_slice(&std::fs::read(source.path()).ok()?).ok()?;
    let email = match source {
        AccountSource::Claude(_) => json
            .pointer("/oauthAccount/emailAddress")?
            .as_str()?
            .to_string(),
        AccountSource::Codex(_) => {
            let token = json.pointer("/tokens/id_token")?.as_str()?;
            jwt_claims(token)?.get("email")?.as_str()?.to_string()
        }
    };
    (!email.is_empty() && !email.chars().any(char::is_control)).then_some(email)
}

fn jwt_claims(token: &str) -> Option<serde_json::Value> {
    let payload = token.split('.').nth(1)?;
    let bytes = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(payload.trim_end_matches('='))
        .ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub(crate) fn account_label(base: &str, account: Option<&str>) -> String {
    match account {
        Some(account) => format!("{base} · {account}"),
        None => base.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sources_follow_the_agent_environment() {
        let home = Path::new("/home/me");
        assert_eq!(
            account_source(
                "claude",
                b"CLAUDE_CONFIG_DIR=/home/me/.claude-keemakr\0",
                Some(home)
            ),
            Some(AccountSource::Claude(
                "/home/me/.claude-keemakr/.claude.json".into()
            ))
        );
        assert_eq!(
            account_source("claude", b"CLAUDE_CONFIG_DIR=\0", Some(home)),
            Some(AccountSource::Claude("/home/me/.claude.json".into()))
        );
        assert_eq!(
            account_source("codex", b"", Some(home)),
            Some(AccountSource::Codex("/home/me/.codex/auth.json".into()))
        );
        assert_eq!(
            account_source("codex", b"CODEX_HOME=/x\0", Some(home)),
            Some(AccountSource::Codex("/x/auth.json".into()))
        );
        assert_eq!(account_source("pi", b"", Some(home)), None);
    }

    #[test]
    fn reads_claude_and_codex_logins_and_tolerates_logouts() {
        let dir = std::env::temp_dir().join(format!("herdr-account-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let claude = dir.join(".claude.json");
        std::fs::write(&claude, r#"{"oauthAccount":{"emailAddress":"a@b.com"}}"#).unwrap();
        assert_eq!(
            read_account(&AccountSource::Claude(claude.clone())).as_deref(),
            Some("a@b.com")
        );
        std::fs::write(&claude, r#"{"projects":{}}"#).unwrap();
        assert_eq!(read_account(&AccountSource::Claude(claude)), None);

        let claims = base64::engine::general_purpose::URL_SAFE_NO_PAD
            .encode(br#"{"email":"c@d.com","sub":"x"}"#);
        let auth = dir.join("auth.json");
        std::fs::write(
            &auth,
            format!(r#"{{"tokens":{{"id_token":"h.{claims}.s"}}}}"#),
        )
        .unwrap();
        assert_eq!(
            read_account(&AccountSource::Codex(auth.clone())).as_deref(),
            Some("c@d.com")
        );
        std::fs::write(&auth, r#"{"OPENAI_API_KEY":"k"}"#).unwrap();
        assert_eq!(read_account(&AccountSource::Codex(auth)), None);
        assert_eq!(
            read_account(&AccountSource::Codex(dir.join("missing.json"))),
            None
        );
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn label_joins_name_and_account() {
        assert_eq!(
            account_label("claude-kee", Some("r@g.com")),
            "claude-kee · r@g.com"
        );
        assert_eq!(account_label("codex", None), "codex");
    }
}
