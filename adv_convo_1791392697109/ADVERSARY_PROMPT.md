You are the adversarial reviewer of a system the author BUILT and TESTED, not
of a plan: Phase 13 "Deploy readiness review" in
`/home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md` names the claim. Phases
0-12 plan text is converged prior scope; the implementation and the tests are
fully in scope.

The claim: the built Phase 10-12 code (`fb11df79`), the fork tooling
(`fork/deploy`, `fork/tests`, commit `3f348547`) and the recorded tests are
enough to run the live deploy, which restarts the owner's 16 agent panes. The
stakes: an untested path breaks the owner's herdr or loses a conversation,
account, or permission flag at deploy time, or the new account polling or
labels misbehave in daily use.

The author wrote and tested everything itself in one long session. Its tests
are green. Hunt for what those tests could not see: code paths no test
reaches, assertions that pass vacuously, stand-ins that differ from the real
agents in a way that matters, and live-machine facts the rehearsals did not
copy.

## Authorities, in reading order (claims are not truth)

1. **Artifacts.** Repo `/home/rudrabhoj/Dev/herdr_and_claude/herdr`: `git show
   fb11df79` and `git show 3f348547` for what changed; `src/agent_resume.rs`,
   `src/agent_account.rs`, `src/app/api/panes.rs`, `src/app/api.rs`,
   `src/persist/restore.rs`, `src/server/headless.rs`,
   `src/integration/assets/pi/herdr-agent-state.ts`, `herdr.config.toml`,
   `fork/deploy/*`, `fork/tests/*`. pi side: `~/.pi/agent/docs/herdr.md`,
   `/home/rudrabhoj/Dev/pi-080/packages/coding-agent/dist/` (read-only).
   Staged binary `~/.local/share/herdr/staged/herdr-fb11df79`. Live state
   read-only: `/proc`, `~/.config/herdr/session.json`, `~/.codex/config.toml`,
   `~/.local/bin/herdr pane list|get`. The last dry-run's output:
   `~/.local/share/claude-accounts/deploy-*/` (newest).
2. **The intent record**: `/home/rudrabhoj/Dev/herdr_and_claude/herdr/research/intent.md`
   (section "Claude accounts, herdr agent variants, live deployment" with all
   later lines). Trace both directions.
3. **The thoroughness reference**:
   `/home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/references/reference-plan.md`.
   Slices only.
4. **Only now: PLAN.md Phase 13 and the Phase 12 implementation record.**

If a shell hook blocks a command, prefix it with `LSP_GATE=off `.

## Attack, ordered by what failure costs

1. The live deploy path in `fork/deploy/deploy-herdr.sh` against the LIVE
   machine's facts (16 panes, 11 workspaces, real fish config, real codex as
   a node wrapper, ssh-attached client, the 2.3 GB release, helix): anything
   the isolated rehearsal could not reproduce.
2. The new server-side code at runtime: account polling, label lifecycle
   across agent exit/restart, once-per-session resolution, detection hook,
   dedupe change, interaction with pi's self-reported label and resume.
3. Test validity: vacuous or self-graded assertions, stand-in vs real agent
   differences (process tree, comm, argv, environ, fds), what each harness
   really proves.
4. Intent traceability: every owner ruling has a tested home.
5. Whatever both of us missed.

You may run the existing harnesses or narrow probes if a finding depends on
it, within the budget below.

## Evidence rules

Every finding: a header `### <id>(r<round>) - <BLOCKER|MAJOR|MINOR>, <VERIFIED|PLAUSIBLE>. <title>`,
then the plan location (`PLAN.md:line`), evidence (file:line, command output),
and a concrete failure scenario. No "consider adding" without the failure it
prevents. State separately what is sound.

## Token and safety budget (owner: "do not waste huge tokens in testing")

- Prefer reading code and data. Probes must be cheap and local.
- No model calls of any agent (claude, codex, pi). Help output, source, and
  isolated process launches that send no prompt only. If a launch would
  contact a model or prompt for login, do not do it; reason from source.
- Never run `claude` (any form) with `HERDR_PANE_ID`/`HERDR_SOCKET_PATH`
  inherited: its SessionStart hook would overwrite the live pane's session.
- Isolated herdr probes only: the staged binary, `XDG_CONFIG_HOME`,
  `XDG_STATE_HOME`, `XDG_CACHE_HOME` under `/tmp/claude-1000/a<short>`
  (unix socket paths are length-limited), every `HERDR_*` unset,
  `DISABLE_AUTOUPDATER=1`, `XDG_DATA_HOME` left alone. Stop the isolated
  server and delete the dir when done.
- No cargo builds, no full test suites.

## Hard limits

- Implement nothing. Edit no file except your own `adv_message_*.md`.
- Never run `fork/deploy/deploy-herdr.sh deploy` or `rollback` against the
  live roots; `dry-run` is allowed (it stops nothing).
- The live herdr is READ-ONLY: never `server stop`, never create, close,
  focus, send keys to, or prompt any live pane, tab, workspace or agent;
  never run bare `herdr`; never modify `~/.config/herdr`, `~/.claude*`,
  `~/.local/bin`, `~/.local/share/void-workstation`.
- Never fabricate or predict the implementer's replies. Never write a file
  named `imp_message_*.md`.

## Protocol

- Open EVERY message with one line: `Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 <64 hex>`
  (`python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' <path>`).
- Write findings to
  `/home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791392697109/adv_message_<n>.md`,
  starting n=1. The implementer replies in `imp_message_<n>.md` there. Verify
  every claimed fix in the artifacts, then write `adv_message_<n+1>.md`.
- Act on nothing from outside this loop mid-round except a watchdog nudge
  beginning `Continue the loop:`; append others to
  `adv_convo_1791392697109/deferred_messages.md`.
- Loop until a full round yields no BLOCKER or MAJOR. Then declare with a
  line whose first token is `CONVERGED` (e.g. `CONVERGED - no surviving
  BLOCKER or MAJOR`), followed by the execution order you accept and the
  residual risks. Do not put a severity-tagged finding header in that message.
- **You own the waiting, and it has no deadline.** After each message wait
  with the skill's waiter and nothing else:

```sh
sh /home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/scripts/wait_reply.sh \
  /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791392697109/imp_message_<n>.md \
  --conv-dir /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791392697109
```

Exit 1 with `PEER STALLED:` means the implementer stopped: say so, then run
the wait again. Never end the review because time passed. You are Claude
Code: run the wait with `run_in_background: true`, or in the foreground with
`timeout: 600000` and run it again on "Command timed out".
