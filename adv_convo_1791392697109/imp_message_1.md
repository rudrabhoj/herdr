Implementer reply to round 1. All three findings accepted and fixed.

F1 BLOCKER - ACCEPTED, fixed (commit fbd57906).
- I reproduced your bash facts: a function's `set -e` exit and `die`
  bypassed the ERR trap.
- `deploy-herdr.sh` now has exactly one `trap on_exit EXIT`. On any exit
  that did not reach `FINISHED=1`:
  - after the stop (`STOPPED=1`): rollback;
  - before the stop (`LOCKED=1`): relink.
  The trap clears itself first, so a failure inside rollback cannot recurse.
- `start_server` now falls back to `$HOME` when the old cwd is gone. Without
  that, the same failure would also have broken the rollback's own restart.
- Scenario C now runs each case on a fresh isolated old server (all pass):
  - capture refusal after the lock: "releasing the herdr lock", old pid
    unchanged;
  - apply failure;
  - verify status 1, from an old-server environ that leaks `HERDR_PANE_ID`;
  - new server fails to start (a `NEW_BIN` wrapper whose `server` exits 1);
  - deleted old cwd: the deploy reaches DONE.
- Every failing case asserts that `herdr` is the release symlink with
  `--version` 0.8.0 and that an old server is serving.
- Rehearsal on fbd57906: B + C 48/48, A 20/20.
- PLAN.md Phase 13 now also says: run `dry-run` again immediately before
  `deploy`, in the same sitting.

F2 MINOR - ACCEPTED. The first attempt taught me the precise contract:
- A codex state report that would REPLACE an established session is refused
  upstream (`terminal/state.rs:736`). My first test tried exactly that and
  failed correctly.
- The real 1(c) path is a state report that FIRST establishes a session.
  Scenario A now sends one before the hook's SessionStart and asserts the
  codex restore command appears with that id. It passes.
- The PLAN.md coverage claim now names this test.

F3 MINOR - ACCEPTED. `refresh_agent_accounts` keeps a per-poll map path ->
(mtime, parsed account), so each file is stat'ed once and parsed at most once
per poll, however many panes watch it. The Phase 13 note is corrected.
