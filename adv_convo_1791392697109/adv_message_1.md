Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 5dc4d76f5f20b78b6dbd23bd174e24d51a7843fb59d5616dde7b97e3b2f3828b

# Round 1 - adversary

Scope read: `git show fb11df79`, `git show 3f348547`, `fork/deploy/*`,
`fork/tests/e2e_deploy.py` (full), heads of the other harnesses, the live
`/proc` tree of the 16 agent panes, `~/.config/herdr/session.json`, the newest
dry-run dir `~/.local/share/claude-accounts/deploy-20261007T170438/`, the
installed Claude hook, `~/.codex`, `~/.pi/agent`, intent.md, then PLAN.md
Phase 12 record and Phase 13 (`PLAN.md:1438-1496`).

### F1(r1) - BLOCKER, VERIFIED. The automatic relink/rollback does not run for most failures after `lock`

Plan location: `PLAN.md:1462-1465` (G12.3 "injected apply failure rolls back
without leaving the lock"), `fork/README.md` ("Any failure after the stop
rolls back automatically"), Phase 13 claim `PLAN.md:1477-1479`.

Evidence. `deploy-herdr.sh` relies on `trap 'on_error $LINENO' ERR` set
inside `main()` (`deploy-herdr.sh:317`) with `set -euo pipefail` and no
`set -E`/`errtrace`. Two bash facts defeat it:

1. The ERR trap is not inherited by shell functions without `errtrace`. A
   failing command inside a function called from `main` makes `set -e` exit
   the whole script without running `on_error`.
2. `die` is `exit 1` (`deploy-herdr.sh:29`). `exit` never raises ERR.

Probe (isolated script, same `set -euo pipefail`, trap set inside `main`):

```
== direct   (false in main)          -> TRAP fired, rc=1
== nested   (false inside inner())   -> no trap, rc=1
== die      (die x)                  -> "die: x", no trap, rc=1
== pipe     (false | tee in main)    -> TRAP fired, rc=1
```

Scenario C passes only because the injected failure is `python3 "$MIGRATE"
apply ... | tee`, which sits directly in `main` (`:338`), the one shape that
does trigger the trap. Paths no test reaches, all after `LOCKED=1; lock`
(`:328`):

| Line | Failure | State left |
|---|---|---|
| `:120` in `capture()` | migrate `capture` exits 1 on any PROBLEM | `~/.local/bin/herdr` stays the lock stub, old server running, no FAIL line in the log |
| `:121` in `capture()` | `die "socket owner changed"` | same |
| `:332` | `die "old server ... did not exit"` | lock stub, `STOPPED=1`, no rollback |
| `:345` `drop_codex_pane` (nested python) | any error | promoted to new release, NO server started, panes gone |
| `:350` `start_server` (nested) | any error | same |
| `:353` | `die "new server did not come up correctly"` (verify status 1: no new pid in 30 s, exe mismatch, or CLAUDE_CONFIG_DIR/HERDR_PANE_ID in the server env) | new release promoted, whatever server state verify rejected, no rollback, no manual resume list printed |

Concrete failure scenario (the likely one). The dry-run capture passed at
17:04:39, but the deploy captures again later, and `capture` is deliberately
strict: it refuses if any snapshot Claude pane lacks a process, if a Claude
process is not yet in the snapshot ("save pending?"), or if a codex process
does not hold exactly one rollout + writer-lock pair
(`migrate-herdr-resume.py:131-133`), for example a freshly opened codex with
no conversation yet, or a codex with a second thread open. Any of those at
deploy time: `capture()` exits under `set -e`, `on_error` never runs, the
`herdr` on PATH is left as the stub "herdr upgrade in progress - wait for
DONE", and DONE never comes. The README tells the operator to run the deploy
with stdout and stderr sent to `/dev/null`, so the only trace is PROBLEM lines
in `$RUN/log`. The old server keeps running, so the owner notices only when
`herdr` is next typed: reattaching after a detach or ssh drop, the herdr
skill, or `herdr pane ...` from an agent. That is the "breaks the owner's
herdr" stake. The Claude hook talks to the socket directly
(`~/.claude-keemakr/hooks/herdr-agent-state.sh:35,92`), so session reports
still land. That is the only mitigation.

The verify-status-1 path is worse: panes are gone, the release is promoted,
and the rollback, with its printed per-pane resume commands (the planned
safety net for "loses a conversation, account, or permission flag"), never
runs.

Required before the live deploy: every exit after `lock` must go through
the same handler. For example, add `set -E` and make `die` call the handler
(relink when `LOCKED=1` and not stopped, rollback when `STOPPED=1`), or use a
single `EXIT` trap keyed on a `DONE` flag. Extend `e2e_deploy.py` scenario C
(cheap, stand-ins only) with at least three injections: capture failure
(after lock, before stop), verify status 1 (for example a `NEW_BIN` wrapper
whose server leaks `HERDR_PANE_ID`, or a 1 s verify window), and a failure
inside `start_server`. Each must assert the real outcome: `herdr` is the
release symlink, not the stub, and the old server is serving.

### F2(r1) - MINOR, VERIFIED. "Once-per-session state-report resolution ... covered by the stub e2e" is vacuous

Plan location: `PLAN.md:1454-1456`.

Evidence. The new branch is `panes.rs:1594-1599`: resolve when a *state*
report first establishes a session. In `e2e_deploy.py` scenario A, the Claude
session arrives through `pane report-agent-session` (`:228`), codex through
the installed hook's `session` call, which posts `pane.report_agent_session`
(`assets/codex/herdr-agent-state.sh:81`), and pi's state reports carry
`resume_argv`, which the guard `params.resume_argv.is_none()` excludes. No
harness ever sends a state report that carries a session the pane did not
already know, so the branch runs zero times in every recorded test.

Failure scenario. A regression in the `known_session` comparison, for example
`current_session_identity_for_persistence` diverging from
`persisted_agent_session` after a `/clear`, would re-resolve on every turn:
one `/proc` environ+argv read, one label report and one watch reset per turn
per pane. Or it would never resolve, so an agent whose SessionStart was
missed keeps a stale restore argv. Neither shows up in any gate. Low live
impact today, because Claude and codex both report sessions through
`report_agent_session`. Either drop the coverage claim or add one stub step
(a state report with a new session id, then assert one label report and a
restore argv for the new id).

### F3(r1) - MINOR, PLAUSIBLE. The account poll parses the same 254 KB file once per pane on the server loop

Plan location: `PLAN.md:1492-1493` ("account polling cost ... one stat per
watched file").

Evidence. `refresh_agent_accounts` (`panes.rs:1806-1850`) keys watches by
pane, not by file. When the mtime changes, every watch re-reads and re-parses
the file with `serde_json` on the headless loop (`headless.rs:3302-3308`).
Live: 14 panes watch `~/.claude-keemakr/.claude.json`, which is 254,477
bytes, and Claude Code rewrites that file from every running instance. Each
5 s tick that follows a write therefore parses about 3.5 MB of JSON on the
thread that serves input and frames. The claim says "one stat per watched
file", but it is one stat and one full parse per watching pane. CLAUDE.md's
multiplicative-path rule asks for a 1-vs-15-pane measurement when such work
is added, and none was recorded.

Failure scenario. With 14 busy kee panes, a periodic stall of a few tens of
ms every 5 s on the server loop, scaling with the number of panes, not
files. Not a deploy blocker. A path-keyed cache (one stat, at most one read
per distinct file per tick) removes it.

## What is sound (checked, not assumed)

- Live inputs to restore: all 16 snapshot Claude sessions, including mine
  (wY:p5, after the dry-run), have a transcript at
  `<config dir>/projects/<encoded cwd>/<id>.jsonl`. Each captured process's
  `/proc/<pid>/cwd` equals its snapshot `cwd`. The variant, config dir and
  bypass per pane in `capture.json` match `/proc`, and `wY:p2` correctly
  resolves to plain `claude` with no `CLAUDE_CONFIG_DIR`.
- Real codex shape: node wrapper (`comm=MainThread`) plus the native child
  (`comm=codex`, pid 13982). Capture and verify both key on the native child,
  whose argv ends with the session id after `codex resume`. The launch
  profile is stable across restarts for either argv form (unit test uses the
  node form). Dropping `-c model_reasoning_effort=high` loses nothing today:
  `~/.codex/config.toml:2` sets it.
- Account files: `~/.claude-keemakr/.claude.json` resolves to rudrabhoj@gmail.com,
  `~/.claude.json` (plain claude) and `~/.claude/.claude.json` (claude-me) to
  ashima@rudrabhoj.com, and codex `id_token` to rudrabhoj@gmail.com. This
  matches the intent's account ruling.
- pi: `~/.local/bin/pi` is `exec node .../cli.js $argv`, so
  `process.argv.slice(2)` is the user's flags. `--session`, `--thinking`,
  `-a/--approve` and the `model_select` event exist in pi-080. No live pi
  pane exists today.
- The installed Claude hook (v7, SessionStart only, socket direct) is
  compatible with the new server's `report_agent_session`. The lock stub does
  not cut session reports.
- Server stop vs the detached deploy: 0.8.0 kills pane process groups, and a
  `setsid -f` deploy is its own session and group.
- New-server environment: the old server's environ has no `CLAUDE_CONFIG_DIR`
  or `HERDR_*` beyond `HERDR_STARTUP_CWD`, so `start_server` with `env -i`
  is clean.
- No live process other than the 16 agents has `comm=claude` (the native
  binary's helpers do not alias it), so "two claude processes" will not
  trigger falsely today.

## Decision asked (PLAN.md:1495-1496)

F1 must be fixed and its three injections added to scenario C before the live
deploy, at zero model cost. Also, rerun `dry-run` immediately before `deploy`
in the same sitting, because capture's strictness now decides whether
`herdr` gets locked. Real codex and pi end to end can stay untested: the
`/proc`-level facts above cover what deploy depends on.
