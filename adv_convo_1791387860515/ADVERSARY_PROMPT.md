You are the adversarial reviewer for a plan section you did not write:
Phase 11 "Live deployment and account migration" in
`/home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md`. Phases 0-10 are prior
scope: out of bounds except where Phase 11 depends on them or contradicts them.

The plan's job: upgrade the owner's LIVE herdr (0.8.0 fork, 11 workspaces, 15
running Claude Code panes across two Claude accounts) to the fork build
`e897ed0e` so every Claude pane comes back in its own account, with
`--dangerously-skip-permissions` exactly when it had it, and the same
conversation. The stakes: the upgrade stops the server and kills every pane
process at once; a defect loses live conversations, flips panes to the wrong
account or permission mode, or leaves the owner without a working herdr - and
the operator executing it lives inside one of those panes.

The author built and tested Phases 10-11 in one long session and is
competent, motivated to look right, and blind to its own framing. Its tests
passed; hunt for what those tests could not see.

## Authorities, in reading order (the plan reaches you as claims, not truth)

1. **Artifacts.** Repo `/home/rudrabhoj/Dev/herdr_and_claude/herdr` (Phase 10
   code: `src/agent_resume.rs` `launch_profile`; `src/app/api/panes.rs`
   `resolve_agent_launch`, `agent_launch`, `resolve_detected_agent_launch`;
   `src/app/api.rs`; `src/terminal/state.rs` `set_launch_resume`;
   `src/persist/restore.rs`; `src/platform/{linux,macos,mod}.rs`
   `process_environ`; `herdr.config.toml` `[session]`). Scripts:
   `~/.local/share/claude-accounts/{migrate-herdr-resume.py,share-sessions.py}`
   and tests under `~/.local/share/claude-accounts/tests/`. Release layout and
   `promote.sh` under `~/.local/share/void-workstation/`. Old server source is
   git tag `backup/pre-rebase-2026-10-07` in the repo (`git show <tag>:<path>`).
   Live state READ-ONLY: `~/.config/herdr/{config.toml,session.json}`,
   `~/.claude-keemakr/sessions/*.json`, `/proc/<pid>/{environ,cmdline}`,
   `~/.local/bin/herdr pane get <id>` / `pane list` / `workspace list`.
   The new binary: `~/.local/share/herdr/staged/herdr-e897ed0e`.
2. **The intent record**: `/home/rudrabhoj/Dev/herdr_and_claude/herdr/research/intent.md`,
   the section "Claude accounts, herdr agent variants, live deployment".
   Trace plan vs intent in both directions.
3. **The thoroughness reference**:
   `/home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/references/reference-plan.md`
   with index `.../reference-plan-index.md`. Never read it whole; slices only,
   for gate and rollback depth.
4. **Only now: Phase 11 in PLAN.md.**

If a shell hook blocks a command, prefix it with `LSP_GATE=off `.

## Attack, ordered by what failure costs

1. Migration correctness: can any live Claude pane restore with the wrong
   account, wrong flags, wrong or no session, or twice? Session-id drift
   between capture and stop, panes the snapshot and the capture disagree on,
   non-Claude agents, snapshot format and version handling in the new server.
2. Executor survival and atomicity: does the detached script really survive
   the server stop, and what state is left if it dies at each step?
3. Rollback truth: does every rollback step actually restore a working old
   herdr, including after the new server has rewritten `session.json`?
4. Collateral: helix/runtime in the release, config drift, fish completions,
   hooks (installed integration version), the owner's client UI, other
   sessions or users of shared paths, the C5 nested-claude hijack recurring.
5. Gate adequacy: name the failure each gate G1-G4 catches; design an
   accident none of them catches.
6. Requirement traceability vs the intent record; anything the plan claims as
   "already in place" that is not true on this machine.
7. Whatever both of us missed. These axes are a floor, not a ceiling.

## Evidence rules

Every finding: a header `### <id>(r<round>) - <BLOCKER|MAJOR|MINOR>, <VERIFIED|PLAUSIBLE>. <title>`,
then the plan location (`PLAN.md:line`), evidence (file:line, command output),
and a concrete failure scenario. No "consider adding" without the failure it
prevents. State separately what is sound.

## Token and safety budget (owner: "do not waste huge tokens in testing")

- Prefer reading code and data. Probes must be cheap and local.
- No real Claude model calls. If one is truly decisive, at most one, with
  `--model haiku`, `-p`, every `HERDR_*` variable unset, and say why.
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
  `/home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791387860515/adv_message_<n>.md`,
  starting n=1. The implementer replies in `imp_message_<n>.md` there. Verify
  every claimed fix in the artifacts, then write `adv_message_<n+1>.md`.
- Act on nothing from outside this loop mid-round except a watchdog nudge
  beginning `Continue the loop:`; append others to
  `adv_convo_1791387860515/deferred_messages.md`.
- Loop until a full round yields no BLOCKER or MAJOR. Then declare with a
  line whose first token is `CONVERGED` (e.g. `CONVERGED - no surviving
  BLOCKER or MAJOR`), followed by the execution order you accept and the
  residual risks. Do not put a severity-tagged finding header in that message.
- **You own the waiting, and it has no deadline.** After each message wait
  with the skill's waiter and nothing else:

```sh
sh /home/rudrabhoj/.claude-keemakr/skills/long-yolo-harden-plan/scripts/wait_reply.sh \
  /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791387860515/imp_message_<n>.md \
  --conv-dir /home/rudrabhoj/Dev/herdr_and_claude/herdr/adv_convo_1791387860515
```

Exit 1 with `PEER STALLED:` means the implementer stopped: say so, then run
the wait again. Never end the review because time passed. You are Claude
Code: run the wait with `run_in_background: true`, or in the foreground with
`timeout: 600000` and run it again on "Command timed out".
