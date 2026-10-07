Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 f3b9d522bed72cd5c117de0fbe7aeaa8146a2096a43cc33d88167e0709fc4b46

# Adversary round 1 - Phase 11 "Live deployment and account migration"

Probes run, all read-only: `/proc/<pid>/{environ,cmdline}` for every `comm=claude`
and for server pid 4222; `~/.config/herdr/session.json` parsed (16 Claude
`agent_session` records); `migrate-herdr-resume.py capture` run against a
rendered copy of `herdr.config.toml` (scratchpad file, `HERDR_CONFIG_PATH` set,
output to scratchpad); old source read at `backup/pre-rebase-2026-10-07`. No
isolated server was started, no claude was run, nothing live was touched.

### A1(r1) - BLOCKER, VERIFIED. 11 of 16 live panes lose their permission bypass: they run `--permission-mode bypassPermissions`, which the keep list does not keep

Plan: PLAN.md:1086 (goal), 1123-1125 (capture), 1146-1147 (G1), 1153 (G4);
config `herdr.config.toml:100`.

Evidence:
- `/proc/<pid>/cmdline` of the live Claude processes: 11 panes run
  `claude --resume <id> --permission-mode bypassPermissions` (wS:p1, wW:p2,
  wW:p3, wW:p5, wW:p6, wW:p7, wW:p8, wW:p9, wW:pA, wW:pB, wW:pC; pids 9009,
  10131, 9354, 9367, 10137, 10106, 10114, 10120, 10142, 9385, 19477). Only wY:p1 (operator) and wY:p3 use
  `--dangerously-skip-permissions`.
- `herdr.config.toml:100`: `resume_keep_args = { claude = ["--dangerously-skip-permissions"] }`.
- The capture itself, run against the rendered new config, prints for every one
  of those 11 panes `claude-kee --resume <sid>` with NO permission flag
  (e.g. `wW:p3: claude-kee --resume <sid>`), while wY:p1 gets
  `claude-kee --dangerously-skip-permissions --resume <sid>`.
- The code already supports the value form: `src/agent_resume.rs:1086-1120`
  keeps `--permission-mode plan` under the entry `"--permission-mode="`, and
  `src/config/model.rs:282` documents that exact entry. The shipped config
  simply omits it.

Failure: after deploy, 11 kee panes (the whole po-l01..po-l10
fleet plus covalent) come back in default permission mode and stall on the
first tool prompt. This violates the RULED intent ("if dangerously bypass
permissions shit is enabled it resumes with that"). No gate sees it: G1 checks
"capture matches the snapshot", and G4 checks "correct flags" against
expectations that, per the plan, come from the same capture (its own oracle).
The e2e_migration rehearsal checks typed text equals the capture's argv
(`tests/e2e_migration.py:118-121`), so it is blind to the same omission.

Required: add `"--permission-mode="` to `resume_keep_args.claude` in the config
that both capture and the new server read, and make G1 compute "bypass active"
per pane independently from `/proc/<pid>/cmdline` (either flag form) and assert
it equals "bypass present in the captured argv", pane by pane, before stop.

### A2(r1) - BLOCKER, VERIFIED. The new server inherits the operator's Claude environment; the plain-`claude` pane restores into the kee account and every future plain `claude` becomes kee

Plan: PLAN.md:1134 (step 9 `setsid -f herdr server` from the deploy script),
1139-1140 (script launched by the operator).

Evidence:
- `/proc/9008/environ` (operator in wY:p1): `CLAUDE_CONFIG_DIR=/home/rudrabhoj/.claude-keemakr`,
  `HERDR_PANE_ID=wY:p1`, `HERDR_SOCKET_PATH`, `HERDR_ENV=1`. A Bash-tool child
  of a Claude pane additionally carries `CLAUDECODE=1`, `CLAUDE_CODE_SESSION_ID`,
  `CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDE_PID`, `CLAUDE_EFFORT`,
  `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_EXECPATH`,
  `CLAUDE_CODE_SESSION_ATTENDED`, and `SHELL=/bin/bash` (checked in my own
  pane, same launcher).
- `/proc/4222/environ` (the live server): none of those. Keys are
  `BUN_INSTALL EDITOR HERDR_STARTUP_CWD HOME LANG LOGNAME ... PATH PWD SHELL(=/usr/bin/fish) SSH_* TERM USER VISUAL nvm_current_version`.
- `src/pane.rs:173-209` (`apply_pane_launch_env`) strips only `CODEX_THREAD_ID,
  OMPCODE, CLAUDECODE, CLAUDE_CODE_CHILD_SESSION, CLAUDE_CODE_SESSION_ID,
  CLAUDE_CODE_MESSAGING_TOKEN`. `CLAUDE_CONFIG_DIR` and the rest pass straight
  into every pane shell.
- Every e2e that "proved" accounts removed this exact variable from the server
  env first: `tests/e2e_variants.py:21-22`, `tests/e2e_migration.py:20-21`
  (`ENV.pop("CLAUDE_CONFIG_DIR")`, `HERDR_*` stripped). The tests could not see it.

Failure: wY:p2 restores as `claude --resume e9b28f98...` (variant `claude`
types plain `claude`), inside a fish whose env has
`CLAUDE_CONFIG_DIR=~/.claude-keemakr`, so it runs in the KEE account. Phase 10
then reads that process env, matches `claude-kee`, and records it, so the flip
persists across all later restores. Every pane shell for the server's lifetime
also has the kee dir, so any new plain `claude` the owner types is kee: the
directory/env auto-switch the owner RULED "should not exist" comes back
globally. Secondary: `HERDR_PANE_ID=wY:p1` in the server env reaches any launch
that uses `PaneLaunchIdentity::Inherit` (`src/persist/restore.rs:572-580` falls
back to Inherit when a pane has no public id; `src/pane.rs:195`), which is the C5
hijack shape; `CLAUDE_EFFORT`/`CLAUDE_CODE_EXECPATH`/`CLAUDE_PID` silently pin
effort and version for all restored Claudes.

Required: capture `/proc/4222/environ` before stop and start the new server with
`env -i` plus exactly that environment (the env every live pane was born
with), not the deploy script's. G4 must assert wY:p2's process has
`CLAUDE_CONFIG_DIR` unset and a fresh shell pane has no `CLAUDE*`/`HERDR_PANE_ID`
leak beyond its own id.

### A3(r1) - MAJOR, VERIFIED. The only abort after the stop produces exactly the C2 outcome; capture is keyed by session id although variant and flags are per-process facts

Plan: PLAN.md:1120-1130 (steps 2-6), 1129-1130 (abort), 1100-1104 (C1/C2).

Evidence:
- `migrate-herdr-resume.py:80` keys the capture by `session_id`; `apply`
  matches only `agent_session.value in found` (`:95`).
- Step 6 aborts "if any captured session is unmatched" - at a point where
  pid 4222 is already gone and every pane process is dead. The plan says
  nothing restarts after that abort; `current` still points at 20260906
  (promote is step 8), and old `src/server/autodetect.rs:290`
  (`auto_detect_launch`, tag) makes the next bare `herdr` autostart the OLD
  server, which ignores `agent_resume` and restores every Claude pane as
  `claude --resume <id>` (C2: personal account, no bypass) - the failure this
  phase exists to prevent.
- Drift window: precondition (step 1) -> `cp -al` of a 2.3 GB tree (step 2) ->
  capture (3) -> backups (4) -> stop (5). Any `/clear` or in-process `/resume`
  in any of 16 Claude panes, several autonomous, changes the snapshot's
  `agent_session` while the captured key stays old -> step 6 aborts post-stop.
- The snapshot can key by pane: each workspace stores `public_pane_numbers`
  (checked on wY), so `wY:p<n>` from `HERDR_PANE_ID` maps to a snapshot pane.

Required: move release staging before step 1; capture last, immediately before
stop; key the capture by pane id and apply the captured variant+kept args with
the snapshot's final session id; after the stop, never abort to the default
restore path - a pane that cannot be matched must be left un-resumed (drop its
`agent_session`, print its manual resume command) rather than restored through
`claude --resume` in the wrong account.

### A4(r1) - MAJOR, PLAUSIBLE. Owner reattach race starts the old server mid-deploy, and step 9 cannot tell

Plan: PLAN.md:1127, 1132-1137 ("The owner reattaches with `herdr`"), 1139-1140.

Evidence: the owner is attached over SSH (`/proc/4222/environ` has
`SSH_CONNECTION`/`SSH_TTY`; client pid 25976 runs
`releases/20260906/bin/herdr`). Step 5 kills that client's server, so the
owner's screen drops at that moment. A bare `herdr` autostarts a server when
none listens (old `autodetect.rs:5,290`). Until step 8, `~/.local/bin/herdr`
resolves to 0.8.0.

Failure: owner retypes `herdr` during steps 5-8 -> 0.8.0 autostarts and
restores the unpatched (or freshly patched, ignored) snapshot -> C2 outcome for
15 panes. Step 9's `setsid -f herdr server` then fails or races, while
`herdr status` and "workspace count = 11" PASS against the old server. Only the
argv check notices, after the damage, with no defined reaction.

Required: the owner must be detached and told not to run `herdr` before a
DONE marker (stated in the runbook and printed by the script), and step 9 must
assert that the server answering is the one it spawned (new pid, version
0.9.3), aborting loudly otherwise.

### A5(r1) - MAJOR, VERIFIED. Rollback is prose with no trigger, no executor, and it restores every kee pane in the wrong account

Plan: PLAN.md:1142-1143, 1150-1152 (G3).

Evidence:
- Rollback "start the old server" with the restored old config: 0.8.0 has no
  variant support, so every Claude pane restores as `claude --resume <id>`
  (C2) - rollback reproduces the failure it is meant to undo. The old server
  does support `[session] resume_agents_on_restore = false`
  (`src/config/model.rs:273,279` at the tag), which the plan does not use.
- No trigger is defined: the operator is dead after step 5; step 9 failure
  says "then exit"; the owner has no command to run.
- "pre-migration `session.json`" is ambiguous: step 4's backup is taken while
  the old server still writes (older than the final save at stop, old
  `src/app/mod.rs:1148-1151`), while `apply` writes
  `session.json.pre-variant-migration` from the final save
  (`migrate-herdr-resume.py:106-107`). They differ whenever anything moved.
- G3 only records whether 0.8.0 can read the new snapshot; it never runs the
  rollback.

Required: a `deploy-herdr.sh rollback` that the script itself invokes on any
post-stop failure and the owner can run by hand; it switches `current` back,
restores the old config plus `resume_agents_on_restore = false`, restores the
final-save backup, starts 0.8.0 with the clean env (A2), and prints the
captured per-pane commands (or types them) so accounts and bypass survive the
rollback. G3 rehearses that command end to end on the isolated copy.

### A6(r1) - MINOR, VERIFIED. Hard-coded counts are already stale and their failure has no consequence

Plan: PLAN.md:1083-1084, 1135-1136, 1146-1147, 1153.

Evidence: live now has 16 Claude processes on the live socket (15 kee incl.
wY:p3, 1 plain), not "15: 14 kee, 1 plain"; the capture printed 16. Step 9
and G1/G4 compare against 15/11 literals.

Failure: step 9 reports a mismatch on a perfectly good deploy (or, after
panes close, passes a bad one), and nothing defines what a mismatch does.
Required: derive the expected set from the capture (pane id -> config dir,
argv) and define mismatch as a rollback trigger or an explicit report-only.

### A7(r1) - MINOR, PLAUSIBLE. G2 tests detachment against the wrong stopper and the wrong launcher

Plan: PLAN.md:1148-1149, 1139-1140.

Evidence: G2 stops an isolated server of the staged NEW binary; step 5 stop is
done by 0.8.0. The script is launched from the operator's Claude Bash tool,
not a plain pane shell. 0.8.0's Linux kill path is process-group based
(`src/detect/mod.rs:1360` at the tag), so `setsid -f` should survive.
Failure if wrong: script dies mid-step with the server stopped. Required: run
G2 with `releases/20260906/bin/herdr` as the isolated server and launch the
`setsid -f` from a child of a non-interactive process in the pane, the way the
operator will.

## Sound (checked, no finding)

- Final snapshot is saved at loop exit before panes are torn down (old
  `src/app/mod.rs:1148-1151`), so step 5's "session.json stops changing" sees
  live `agent_session` values.
- Live snapshot and live processes agree today: 16 Claude `agent_session`
  values equal the 16 registry session ids.
- Rendered new config is a strict superset of the live config (only
  `default_shell` placeholder and `[session]` differ).
- Shared session store symlinks are in place as claimed (7 links checked; the
  plain pane's transcript resolves through `~/.claude/projects`).
- Restore types the resume command into the pane's fish shell
  (`src/agent_resume.rs:56-57`), so fish-function variants work.
- Installed Claude hook is integration v7 vs shipped v10; the diff is event
  filtering only, `pane.report_agent_session` unchanged. Expect an
  "outdated integration" badge, not a break.
- `cp -al` then replacing `bin/herdr` cannot corrupt the old release through
  the shared inode while 0.8.0 runs it (ETXTBSY), and the plan says new inode.
