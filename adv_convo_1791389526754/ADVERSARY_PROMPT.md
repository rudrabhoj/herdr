You are the adversarial reviewer for a plan section you did not write:
Phase 12 "pi, codex, and the untested angles" in
`/home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md`. Phases 0-11 are prior
scope (Phase 11, the live deployment, converged in
`/home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791387860515`): out of
bounds except where Phase 12 depends on or contradicts them.

The plan's job: make pi and codex panes survive a herdr restart like Claude
panes (same conversation, same launch flags), and close the Claude angles the
author never exercised. The stakes: the live codex pane `wS:pW` runs with
`--dangerously-bypass-approvals-and-sandbox` and a pinned model; a defect
restores it as a bare shell, or restores it with the wrong flags or session,
and installing herdr's integrations touches the owner's ~/.codex config and
15+ custom pi extensions.

The author wrote this plan by listing what it had NOT tested. That list is
its own framing: hunt for the angles it still does not see.

## Authorities, in reading order (the plan reaches you as claims, not truth)

1. **Artifacts.** Repo `/home/rudrabhoj/Dev/herdr_and_claude/herdr`:
   `src/agent_resume.rs` (`plan`, `launch_profile`, `kept_launch_args`),
   `src/app/api/panes.rs` (`resolve_agent_launch`, `agent_launch`),
   `src/persist/restore.rs`, `src/integration/` (codex and pi install logic and
   `src/integration/assets/{codex,pi}`), `herdr.config.toml`. Migration script
   `~/.local/share/claude-accounts/migrate-herdr-resume.py`. CLIs, help only:
   `codex --help`, `codex resume --help`, `pi --help`. Read-only live state:
   `/proc/<pid>/{cmdline,environ,fd}`, `~/.codex/config.toml`,
   `~/.pi/agent/{extensions,settings.json}`, `~/.config/herdr/session.json`,
   `~/.local/bin/herdr integration status`, `~/.local/bin/herdr pane get <id>`.
   New binary: `~/.local/share/herdr/staged/herdr-e897ed0e`.
2. **The intent record**: `/home/rudrabhoj/Dev/herdr_and_claude/herdr/research/intent.md`,
   section "Claude accounts, herdr agent variants, live deployment" including
   the later pi/codex lines. Trace both directions.
3. **The thoroughness reference**:
   `/home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/references/reference-plan.md`
   (index `.../reference-plan-index.md`). Slices only.
4. **Only now: Phase 12 in PLAN.md.**

If a shell hook blocks a command, prefix it with `LSP_GATE=off `.

## Attack, ordered by what failure costs

1. Restore correctness for codex and pi: session identity (codex rollout fd,
   forks, `codex resume` semantics, pi session path), flag placement and
   whether kept flags actually take effect, values that validation rejects.
2. Integration install side effects on the owner's codex config and pi
   extensions; what the installed hooks do at runtime (latency, failures,
   prompts) and whether they report what restore needs.
3. Migration extension: adding `agent_session` for codex to a 0.8.0 snapshot;
   anything the new server then does with it.
4. The Claude angles in step 6 and the residual list: anything mis-ranked as
   residual that should block.
5. Gate adequacy, and whether the gates can run without model calls.
6. Whatever both of us missed.

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
  `/home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791389526754/adv_message_<n>.md`,
  starting n=1. The implementer replies in `imp_message_<n>.md` there. Verify
  every claimed fix in the artifacts, then write `adv_message_<n+1>.md`.
- Act on nothing from outside this loop mid-round except a watchdog nudge
  beginning `Continue the loop:`; append others to
  `adv_convo_1791389526754/deferred_messages.md`.
- Loop until a full round yields no BLOCKER or MAJOR. Then declare with a
  line whose first token is `CONVERGED` (e.g. `CONVERGED - no surviving
  BLOCKER or MAJOR`), followed by the execution order you accept and the
  residual risks. Do not put a severity-tagged finding header in that message.
- **You own the waiting, and it has no deadline.** After each message wait
  with the skill's waiter and nothing else:

```sh
sh /home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/scripts/wait_reply.sh \
  /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791389526754/imp_message_<n>.md \
  --conv-dir /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791389526754
```

Exit 1 with `PEER STALLED:` means the implementer stopped: say so, then run
the wait again. Never end the review because time passed. You are Claude
Code: run the wait with `run_in_background: true`, or in the foreground with
`timeout: 600000` and run it again on "Command timed out".
