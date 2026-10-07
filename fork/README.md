# Fork tooling

Tooling that exists only in this fork (`rudrabhoj/herdr`), not upstream. `PLAN.md` at the repo root has the full design history: Phases 10-12, their adversarial reviews, and the gate results.

## What the fork adds to herdr

| Feature | Where | Why |
|---|---|---|
| Tab, space, agent and pane modes | `src/client/shell/control.rs` | zellij-style sticky modes, Phases 1-9 |
| Agent variants | `[[session.agent_variants]]`, `src/agent_resume.rs` `launch_profile` | `claude-kee` and `claude-me` differ only by `CLAUDE_CONFIG_DIR`. herdr shows and restores the variant a pane last ran. |
| Kept launch flags | `session.resume_keep_args` | A restore keeps flags such as `--dangerously-skip-permissions`, `--permission-mode bypassPermissions`, and codex's `-m`/`--search`/bypass. Kept flags go after a subcommand (`codex resume <flags> <id>`). |
| Account in the agent label | `ui.show_agent_account`, `src/agent_account.rs` | Labels read like `claude-kee · me@example.com`. Claude and codex are read from the agent's own config dir and polled for login changes. pi reports its own account through its extension. |
| pi restore command | `src/integration/assets/pi/herdr-agent-state.ts` | pi's `process.title` wipes `/proc/<pid>/cmdline`, so the extension reports pi's flags itself. |

## deploy/

| Script | Purpose |
|---|---|
| `share-sessions.py` | Shares Claude's session stores (`projects`, `file-history`, ...) between two `CLAUDE_CONFIG_DIR`s through symlinks. Logins stay separate. |
| `migrate-herdr-resume.py` | One-time bridge from a pre-variant herdr. `capture` reads each live Claude and codex pane's variant, flags and session (codex from its open rollout and writer-lock fds). It refuses unless the captured set equals the server's own record. `apply` writes `agent_resume` into the old server's final snapshot. `selftest` pins the codex command to what the server re-derives. |
| `deploy-herdr.sh` | `dry-run`, `deploy` or `rollback` of the live void-workstation herdr (Phase 11 plus Phase 12). It stages a release, locks `herdr`, captures, stops, applies, installs the codex and pi integrations (non-fatal), promotes, then starts the new server with the old server's exact environment and verifies every pane. Any failure after the stop rolls back automatically. Every root is a variable. |

Run `deploy` detached, because the operator usually lives in one of the panes it restarts:

```sh
NEW_BIN=~/.local/share/herdr/staged/herdr-<sha> setsid -f fork/deploy/deploy-herdr.sh deploy </dev/null >/dev/null 2>&1
```

## tests/

Every harness runs in isolated XDG roots under `/tmp/claude-1000`, with every `HERDR_*` variable stripped, and checks at the end that the live herdr is unchanged.

| Harness | Proves | Model calls |
|---|---|---|
| `e2e_modes.py` | The keyboard modes, against the fork config. | none |
| `e2e_variants.py` | Real Claude in four variant and flag combinations, each restored after a server restart, with the conversation intact. | about 8 short turns |
| `e2e_migration.py` | The new server restores a fake-id copy of the live 0.8.0 snapshot. | none |
| `e2e_deploy.py` | Stand-in claude, codex and pi. Account labels follow login changes. Full deploy from the operator's env, rollback, an injected install failure, and an injected apply failure. | none |
| `e2e_claude_angles.py` | `/clear` and `/resume` move the recorded session, and `claude-me`'s picker lists `claude-kee` sessions. | 1 haiku |

The stand-ins only work if they come first on PATH inside the isolated fish. `e2e_deploy.py` aborts before starting anything if fish would resolve a real agent.
