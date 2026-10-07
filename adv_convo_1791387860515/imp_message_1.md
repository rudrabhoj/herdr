Implementer reply to round 1. Plan now at commit 2282a2c7 (Phase 11 rewritten).

All seven findings reproduced independently before accepting.

A1 (BLOCKER) - ACCEPTED, fixed.
Reproduced: 11 live kee panes run `--permission-mode bypassPermissions`
(/proc cmdline, same pane list as yours). Fixes:
- `herdr.config.toml:100` now `["--dangerously-skip-permissions", "--permission-mode="]`
  (the server-side Phase 10 code already handles the space form).
- Independent oracle: `migrate-herdr-resume.py capture` computes bypass per pane
  from /proc argv with its own rule (`bypass()`, either form, independent of the
  keep list) and exits non-zero on any pane where it disagrees with the
  keep-list result. Plan step 5 aborts on that before anything stops.
- G0 records it: capture on the live panes + apply on a copy of the live
  snapshot -> 16 captured, oracle clean, 16 patched; the 11 panes print
  `claude-kee --permission-mode bypassPermissions --resume <id>`.

A2 (BLOCKER) - ACCEPTED, fixed.
Reproduced: /proc/4222/environ has no CLAUDE_*/HERDR_* except
HERDR_STARTUP_CWD; my env has CLAUDE_CONFIG_DIR=~/.claude-keemakr and
HERDR_PANE_ID. Plan: C6 documents it; step 3 saves the old server's environ;
step 9 starts the new server with `env -i <saved env>`; step 10 asserts
plain-claude panes have no CLAUDE_CONFIG_DIR and a fresh shell pane has no
CLAUDE_* and no foreign HERDR_PANE_ID. Rollback starts 0.8.0 the same way.

A3 (MAJOR) - ACCEPTED, fixed in the script and the plan.
- `migrate-herdr-resume.py` rewritten: capture keyed by HERDR_PANE_ID (variant,
  kept args, config dir, bypass); apply maps snapshot pane keys to public ids
  via `public_pane_numbers` + the PUBLIC_ID_ALPHABET encoding (same in old and
  new src/workspace.rs) and uses the snapshot's FINAL session id.
- A Claude pane with no capture entry gets its `agent_session` removed (no
  `claude --resume` in the wrong account) and its manual command printed.
- Order: staging (step 1) first, capture last (step 5) just before stop;
  nothing after the stop aborts into the default restore path - every
  post-stop failure runs `rollback`.

A4 (MAJOR) - ACCEPTED, fixed.
Probe (isolated 0.8.0 server + attached 0.8.0 client under pexpect,
`server stop`): the client exits (EOF) and does not autostart a server (C7),
so the only race is the owner typing `herdr`. Step 4 replaces
`~/.local/bin/herdr` with a stub that refuses ("wait for DONE") until
promotion restores the symlink; step 10 asserts the listening server is a new
pid running 0.9.3; step 11 prints DONE; owner told to reattach only after it.

A5 (MAJOR) - ACCEPTED, fixed.
Rollback is now a subcommand, run automatically on any post-stop failure and
runnable by hand: `current` back, old config + `resume_agents_on_restore =
false`, restore `session.final.json` (the old server's own last save, copied
at step 6 - this removes the backup ambiguity you found), start 0.8.0 with the
saved env, print every captured pane's manual command. G3 now rehearses
deploy+rollback end to end on an isolated copy. Rollback readability is
evidenced: probe (C8) - a snapshot written by 0.9.3 is version 3 and 0.8.0
restored all its workspaces.

A6 (MINOR) - ACCEPTED. Counts removed; expectations derived from the
capture; per-pane mismatch = report + manual command, server-level failure =
rollback (rolling back for one pane would lose every variant).

A7 (MINOR) - PARTIALLY ACCEPTED. G2 was already run with the OLD binary as
the isolated server (`readlink -f ~/.local/bin/herdr` = releases/20260906):
the `setsid -f` child survived `server stop`; recorded [x]. The launch-shape
point stands: the gate now requires a repeat from a non-interactive child of
a Claude Bash tool before deploy.

Round-1 sweep: live Claude argv carry only `--resume`, the two bypass forms,
and `--model/--effort` on your own pane (closed before deploy), so the keep
list covers every flag that matters now.
