Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 14a57052dd83ccefeb6d85dd5aa17430059aae1e4097a5250a3d8dfeee8ef92a

# Round 1: adversarial review of Phase 12 (PLAN.md:1273-1344)

Read in the required order: artifacts first (agent_resume.rs, panes.rs, terminal/state.rs,
restore.rs, detect/mod.rs, platform/linux.rs, integration targets/config_file/config_edit,
the codex and pi assets, the migration script, live /proc and config state, the codex/pi help
output, local strings from the installed codex binary), then intent.md, then the reference
index, then Phase 12. I made no model calls and started no agent. My only process launch was a
throwaway `node -e` that sets process.title (A1). I edited nothing except this file.

Six MAJOR, four MINOR, no BLOCKER.

---

### A1(r1) - MAJOR, VERIFIED. pi's launch flags cannot be read from /proc, so the pi keep list does nothing

**Plan**: PLAN.md:1294-1297 (pi facts), 1309 (`resume_keep_args.pi`), 1332-1333 (G12.2 "same for pi").

**Evidence**
- `~/.local/bin/pi` is a fish script: `exec /usr/bin/env node "/home/rudrabhoj/Dev/pi-080/packages/coding-agent/dist/cli.js" $argv`.
- `/home/rudrabhoj/Dev/pi-080/packages/coding-agent/dist/cli.js:11`: `process.title = APP_NAME;`
- On Linux, node's process.title overwrites the argv area. Probe:
  `node -e 'process.title="pi"; ...' -- --model openai-codex/gpt-5.6-sol --thinking max` gives
  `comm=pi` and `/proc/<pid>/cmdline = "pi" + NULs`. Every flag is gone.
- herdr reads argv only from there: `src/platform/linux.rs:763-773` (`process_argv` reads
  `/proc/{pid}/cmdline` and drops empty parts) feeds `agent_launch` (`src/app/api/panes.rs:1742-1760`)
  and then `kept_launch_args` (`src/agent_resume.rs:374`). For the owner's pi that argv is `["pi"]`.

**Failure**: the owner launches `pi --model openai-codex/gpt-6-astra --thinking high` in a pane.
`kept_launch_args(["pi"], …)` returns empty and there is no pi variant, so `launch_profile`
returns `resume_argv: None` (agent_resume.rs:353). The restore runs `pi --session <path>` with
settings.json defaults (`gpt-5.6-sol`, `max`). This is the "same launch flags" failure the plan
exists to prevent. Detection still works, because comm and cmdline both say `pi`, so nothing
looks wrong until a restart. G12.2 can pass vacuously if its pi is started without flags, or
through a stub that does not set process.title.

**Required**: pi's flags must come from inside pi, because `process.argv` in node is not
affected by the title. The herdr pi extension can send `resume_argv` on
`pane.report_agent_session`, which the API already accepts (panes.rs:1610, 1633-1643). It must
then respect the same allowlist semantics, or the plan must state who owns the allowlist. The
plan also needs a gate whose pi stand-in sets `process.title = "pi"`, so the /proc wipe is
reproduced.

---

### A2(r1) - MAJOR, VERIFIED (trust gate exists) / PLAUSIBLE (exact start-up timing). codex 0.159 does not run newly installed hooks until the owner trusts them

**Plan**: PLAN.md:1310-1314 (install, "codex starts … no prompt sent"), 1329-1332 (G12.2 "session
reported"), 1337-1338 (G12.5). The plan never mentions hook trust.

**Evidence**: strings in the installed binary
`…/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex` (codex-cli 0.159.2):
- `Hooks need review` / `1 hook is new or changed.` / `Hooks can run outside the sandbox after you trust them.`
  / `Trust all and continue` / `Continue without trusting (hooks won't run)` / `New hook - review required` /
  `Modified since last trusted - review required`.
- Trust is persisted as `hooks.state."<…>".trusted_hash` in config.toml (`HookStateToml`, `trusted_hash`).
- `codex --help`: `--dangerously-bypass-hook-trust  Run enabled hooks without requiring persisted hook trust for this invocation. DANGEROUS.`
- `herdr integration install codex` (src/integration/targets.rs:160-235) writes `hooks.json` and the
  script. It has no trust handling (searching `src/integration` for `trust` finds nothing).
  `--dangerously-bypass-approvals-and-sandbox` does not cover hook trust; that is a separate flag.

**Failure**
1. Live: after install, the next codex start (the restored `wS:pW`) opens on the review modal
   instead of the conversation. If the owner picks "Continue without trusting", herdr never gets a
   codex SessionStart report. The migration-written `agent_resume` (step 5) is kept by
   `restore_reported_resume`, and the codex state-report guard (terminal/state.rs, the
   `("herdr:codex","codex")` mismatch return inside `set_hook_authority_at`) cannot move it. A later
   `/new` or `/resume <other>` inside codex is invisible to herdr, and the next restart reopens the
   old conversation. That is the "wrong session" outcome in the stakes.
2. G12.2 as written ("session reported") cannot pass in an isolated CODEX_HOME without a trust step.
   The obvious way to make it pass is to add `--dangerously-bypass-hook-trust`, which is a new
   DANGEROUS flag and needs an owner ruling.
3. Step 4's check "codex starts, no prompt sent" will see the modal and has no expected result
   for it.
4. Every reinstall that changes the hook command or its handler config shows "Modified since last
   trusted" again (PLAUSIBLE: what goes into the hash is not visible in strings).

**Required**: name the trust step (the owner trusts once, interactively). Add a check that
`hooks.state` entries for the herdr hook exist in `~/.codex/config.toml` before G12.5 is declared.
Record an explicit decision against, or an owner ruling for, `--dangerously-bypass-hook-trust`.
State what the restored `wS:pW` will show on first start after install.

---

### A3(r1) - MAJOR, VERIFIED. The G12.2 "isolation" reaches the owner's live credentials and files

**Plan**: PLAN.md:1329-1333 (G12.2: isolated CODEX_HOME copy, isolated pi agent dir copy),
1312-1314 (start pi and codex on the live dirs to check them).

**Evidence**
- codex: `~/.codex/auth.json` (ChatGPT login, mode 600) is single-use-refresh. The binary contains
  `Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.`
  A copied CODEX_HOME that refreshes once (on start-up, a 401, or token age) rotates the token in
  the copy and invalidates the owner's original. Codex contacts the backend at start-up even with
  no prompt (`~/.codex/models_cache.json` was rewritten at 16:11 today).
- pi: `~/.pi/agent/extensions/codex-models-sync.ts:21` has `const AGENT_DIR = join(homedir(), ".pi", "agent")`.
  `:46-47` reads the LIVE `auth.json` and fetches `https://chatgpt.com/backend-api/codex/models`
  with the owner's bearer token. `:100` writes the LIVE `~/.pi/agent/models.json`. lsp-telemetry.ts
  writes `~/.pi/agent/telemetry.log` at shutdown. `PI_CODING_AGENT_DIR` (integration/env.rs:35)
  redirects herdr's install, not these extensions. "Isolated agent dir copy" therefore runs network
  calls with the owner's token and writes live files.
- Unverified, and it makes the gate worse: codex's SessionStart hook may fire only when the first
  turn starts. Its payload carries model context (`additionalContext`). If so, "session reported,
  no model calls" is impossible with real codex.

**Failure**: running G12.2 as specified can log the owner out of codex. The live `wS:pW` then
fails on its next turn with "Please log out and sign in again". It also mutates the live pi
models.json. That breaks the owner's ruling "without ruining our current shit" and the brief's "no
model calls / no login prompt".

**Required**: G12.2 must never start a real codex or pi against copied credentials. Put stub
executables named `codex` and `pi` first on the isolated server's PATH (restore types bare names,
agent_resume.rs:56-89). The codex stub records argv and holds an open fake
`sessions/…/rollout-…-<uuid>.jsonl` and `thread-writer-locks/<uuid>.lock`. The real installed
hook script, fed a synthetic `SessionStart` JSON on stdin with `transcript_path`, produces the
report. The pi stub is a node script that sets `process.title="pi"` (A1) and loads the real
herdr pi extension with a fake `ctx`. The step 4 live check should be file-level instead (extension
present, owner files byte-identical to the backup, codex `hooks.json` valid JSON), not a live
start.

---

### A4(r1) - MAJOR, VERIFIED. The codex migration has no independent expected set, so a silent zero-match capture leaves wS:pW a bare shell

**Plan**: PLAN.md:1315-1319 (step 5), 1334-1335 (G12.3, fake ids).

**Evidence**
- In the live `~/.config/herdr/session.json`, `wS` is `workspaces[6]` and `wS:pW` is pane key `58`
  (public number 28, which is `W` in `ALPHABET`). It has no `agent_session` and no other codex
  marker. The 0.8.0 snapshot cannot say "there is a codex pane here".
- Phase 11's guard (`migrate-herdr-resume.py` capture: "The expected set comes from the server's
  own snapshot, not from /proc, so a capture that silently matched nothing … cannot pass", finding
  C1(r3)) therefore cannot cover codex.
- The live codex has two processes with the same flags: pid 13975 (node wrapper, comm `MainThread`,
  pgid leader) and pid 13982 (native, comm `codex`). There is also `codex-code-mode-host`. A comm
  filter or socket mismatch picks the wrong set without any error.
- Session identity: 13982 holds exactly one rollout fd
  (`…/rollout-2026-10-04T20-49-46-01a108ae-0bde-7a62-bbe2-67c00f46bc66.jsonl`) and one
  `thread-writer-locks/01a108ae-….lock`. The timestamp part of the rollout name also contains
  dashes. Sub-agent threads or a mid-flight `/new` can leave several open.

**Failure**: the capture finds zero codex processes (wrong comm, wrong socket, or the node pid with
no fd). Apply adds nothing and exits 0, and `wS:pW` restores as a bare shell, which is the first
stake named. Or the capture picks the first of two rollout fds (a sub-agent thread) and restores
the wrong conversation.

**Required**
- The expected codex set comes from the live server, read-only (`herdr pane list` with
  `agent == "codex"`), taken in the same capture step. Capture refuses on any expected pane it did
  not find.
- Exactly one rollout or writer-lock fd per pane, otherwise PROBLEM. Take the uuid from the lock
  file name, or parse the rollout name from the right.
- Run the codex capture last, as Phase 11 does for Claude: unlike Claude, the snapshot cannot
  correct a session change between capture and stop.
- Deploy report and `rollback` print `codex resume <kept> <id>` and the cwd for each codex pane.
  Phase 11's rollback (PLAN.md, Rollback paragraph) prints only Claude panes.

---

### A5(r1) - MAJOR, VERIFIED. Which binary deploys, and in what order relative to Phase 11, is undefined. One order brings back the unverified flag placement

**Plan**: PLAN.md:1300-1305 (code changes), 1306-1309 (config), 1310 ("after the Phase 11
deploy"), 1315 ("Phase 11 capture/apply extended"). Phase 11 deploys `e897ed0e` (PLAN.md:1083).

**Evidence**
- `git log e897ed0e..HEAD -- src` is empty: the staged `herdr-e897ed0e` is the current source,
  without steps 1-2.
- `launch_profile` splices kept args at index 1 (agent_resume.rs:361):
  `codex <kept> resume <id>`.
- `resolve_detected_agent_launch` (panes.rs:1712-1738) re-derives the resume whenever an agent is
  newly detected and a persisted session exists. A restored pane qualifies.
- `resolve_agent_launch` returns early when the agent has no keep list and no variant
  (panes.rs:1660-1671).

**Failure**
- (a) Deploy ships e897ed0e with step 3's codex keep list in the rendered config. The restored
  codex runs the migration's `codex resume <kept> <id>`. When it is detected, the server overwrites
  that with `codex <kept> resume <id>`, the placement the plan itself marks "unverified to apply"
  (PLAN.md:1287-1288). The next restart may resume without bypass, model or search.
- (b) Phase 12 code ships instead. The deploy target is a new binary, but Phase 11's gates (G0,
  G3, G5, the e2e 44/44 at PLAN.md:1097-1098) were proven on e897ed0e, and nothing says to re-run
  them.
- (c) Step 4 after deploy: the restored codex started before `hooks.json` existed, so it reports
  nothing until its next start (where A2's modal is waiting).
- (d) Capture computes codex kept args from `resume_keep_args.codex`, so the config must be read
  by the capture before step 3 is otherwise "done". The plan does not order these.

**Required**: one explicit execution order. Build and stage a new binary with steps 1-2. Re-run
the Phase 10/11 e2e and G3 against it and update Phase 11's binary references. Step 3 goes into
the rendered config before capture and before the new server starts. Decide whether integration
install happens before the deploy restore (the restored codex starts with hooks and the trust
modal) or after (no tracking until the next codex start), and say which.

---

### A6(r1) - MAJOR, PLAUSIBLE. G12.4's `/resume <other id>` runs against the shared live session store

**Plan**: PLAN.md:1320-1324 (step 6), 1336 (G12.4).

**Evidence**: Phase 11 "Already in place" (PLAN.md:1092-1094): `~/.claude/projects` and related
dirs are symlinks into `~/.claude-keemakr/`. Every account's `/resume` picker lists the
conversations of all live Claude panes (16 in session.json, including this reviewer's
`15050e45-…`). Claude Code resumes in place (it appends to the same JSONL) unless
`--fork-session` is given.

**Failure**: the implementer picks an id from `claude-me`'s picker to prove cross-account listing,
or uses a real id for `/resume <other id>`. A second process now writes to a live pane's
conversation, and that conversation gets entries from the test. The step also leaves throwaway
sessions in the owner's picker. This breaks "without ruining our current shit" and "free up all
resources".

**Required**: G12.4 creates its own throwaway sessions under a `/tmp/claude-1000/a…` cwd. It asserts
that every id it resumes is absent from the live snapshot's `agent_session` set, and it deletes
the throwaway session files and project dir afterwards.

---

### A7(r1) - MINOR, VERIFIED. `server reload-config` swaps the config but does not re-resolve existing panes

**Plan**: PLAN.md:1322-1323, G12.4.

**Evidence**: src/app/mod.rs:927-930 only assigns `agent_variants` and `resume_keep_args`.
Resolution runs only on a session report (panes.rs:1633-1635) or on new agent detection
(panes.rs:1712).

**Failure**: the owner removes `--dangerously-skip-permissions` from the keep list and reloads.
Every running pane still restores with the bypass until its next session report. G12.4 passes if
it tests with a fresh session after the reload. Required: G12.4 states the expected behaviour for
existing panes, either documented as "next report only" or re-resolved on reload.

### A8(r1) - MINOR, PLAUSIBLE. A codex session id first learned from a state report skips the kept-flags resolution

**Evidence**: `src/integration/assets/codex/herdr-agent-state.sh` exits on `session` when
`transcript_path` is empty. `UserPromptSubmit` still sends `agent_session_id` through
`pane.report_agent`. `handle_pane_report_agent` (panes.rs:1554-1597) sets the session through
`HookStateReported` and never calls `resolve_agent_launch`, which runs only in
`handle_pane_report_agent_session` (panes.rs:1633). Because the session was unknown when codex was
detected, `resolve_detected_agent_launch` already returned. The saved resume is then
`codex resume <id>` without flags. The owner's config.toml sets never/danger-full-access/model/effort,
so live, only `--search` is lost. Required: resolve when a state report first establishes the
session, with a unit test.

### A9(r1) - MINOR, VERIFIED. `-c=`/`--config=` persist every override into a 664 file

`stat ~/.config/herdr/session.json` gives `664`. Keeping all `-c` values writes any secret passed
as `-c key="…"` into a world-readable snapshot. The live argv has none; the owner's firecrawl key
lives in config.toml, not argv. Required: document this, or keep `-c` only for an allowlisted key
prefix.

### A10(r1) - MINOR, VERIFIED. Install side effects the plan does not state

`~/.pi/agent` is a git repository (`.git`, `.gitignore`), so `herdr-agent-state.ts` appears as an
untracked file and syncs to the Mac if committed (harmless there: it checks HERDR_ENV, assets/pi:11-19).
The codex keep list lacks `--add-dir=`, `-C=`/`--cd=`, `--enable=`, `--disable=` and
`--no-alt-screen`; pi lacks `--approve`/`-a`, and without it a restored pi may stop on
project-local trust. None are live today. The plan should also say `--worktree` and `--remote` must
never be kept: `--worktree` would create a new worktree on every restore.

---

## What is sound (checked, no finding)

- Step 1's placement is right. `codex resume --help` lists `-m`, `-c`, `--search`,
  `--dangerously-bypass-approvals-and-sandbox`, `-s`, `-a`, `-p` as resume's own options. Claude
  (`--resume`), pi (`--session`) and letta plans keep argv[1] as a flag, so only codex moves.
- codex identification: the pgid leader is the node wrapper (pid 13975 = pgid). Its argv carries
  the full flag set, and `script_arg_agent_name` resolves `…/bin/codex` to codex, so kept args are
  readable for codex (unlike pi, A1).
- Session id: the open rollout's uuid `01a108ae-0bde-7a62-bbe2-67c00f46bc66` matches the open
  `thread-writer-locks/<uuid>.lock` and appears in `session_index.jsonl`.
- `install_codex` config write: `write_config` stages privately and preserves the 0600 mode of
  `~/.codex/config.toml` (config_file.rs:96-117), which matters because that file holds an API key.
  It only appends `[features]\nhooks = true` (no `[features]` table exists today). `codex features
  list` already reports `hooks stable true`, so behaviour does not change. `hooks.json` does not
  exist yet, so nothing is overwritten.
- The codex hook script prints nothing to stdout (no context injected into the model), uses a
  0.5 s socket timeout, and exits 0 on every failure. Established codex sessions cannot be replaced
  by state reports (the codex mismatch guard in `set_hook_authority_at`).
- The pi install writes one file. pi detection itself works because the title is `pi`.
- The resume model mismatch in codex is a warning line ("This session was recorded with model …"),
  not a modal.

## Residual additions I would accept as residual, if stated

- codex `thread-writer-locks`: if an old codex outlives the server stop for a moment, the restored
  `codex resume` may collide with its writer lock. G12.5 should check that the old codex pids are
  gone before calling the result.
- An npm `codex update` between rehearsal and deploy can change hook or resume behaviour. Pin by
  recording `codex --version` in the report.
