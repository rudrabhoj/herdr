Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 535652d61cb7c211d35fb1b88d2a55191e09d1492d3dc9a0d3827c5a7fa5e367

# Round 2 - adversary

CONVERGED - no surviving BLOCKER or MAJOR

## Fixes I checked in the artifacts (I did not take them on trust)

- **F1** (`fbd57906`, `deploy-herdr.sh`):
  - The ERR trap is gone. One `trap on_exit EXIT`, set in `main`, now sees
    every way out of the deploy: a `set -e` exit inside a nested function,
    `die`, and plain failures.
  - It clears itself first. After the stop (`STOPPED=1`) it rolls back.
    Before the stop with `LOCKED=1` it relinks.
  - `FINISHED=1` is set on both success paths: the dry-run exit and the end
    of `main`. After `promote`, `LOCKED=0` while `STOPPED=1`, so a failure in
    the codex wait loop or in `start_server` rolls back. That is right.
  - `rollback` runs in a `||` context, so a failing step inside it does not
    abort the rest.
  - `start_server` now falls back to `$HOME` when the old cwd is gone.
  - Scenario C now covers apply, capture (aborts before the stop, lock
    released, old pid unchanged), verify status 1 (leaked `HERDR_PANE_ID`),
    a new server that fails to start, and a deleted old cwd.
  - Each failing case asserts three real end states: the symlink, which is
    not the stub; `--version` reports 0.8.0; and the `/proc` exe of the
    serving server is the old release. None of these assertions passes
    vacuously.
- **F2** (`5750249f`): the PLAN.md:1455-1458 claim now names a test that
  reaches `panes.rs:1594-1599`. That test is a state report that first
  establishes a codex session. Your note that replacing an established
  session is refused upstream is consistent with `session_report_applied`.
- **F3** (`fbd57906`, `panes.rs:1810-1842`): a per-poll map from path to
  (mtime, parsed account). Each shared file is stat'ed once per poll and
  parsed at most once. `watch.modified` is still compared per pane, so each
  pane's label update is unchanged. Correct.

## Execution order I accept

1. Close this review: manifest `status` not `open`, and no `watchdog.pid`.
   `preconditions` refuses otherwise.
2. **Clear the stale staging first.** `releases/20261007` was hard-link
   staged by the 17:04 dry-run with `herdr-fb11df79`. Plan Phase 11 now
   targets `herdr-fbd57906`. `NEW_REL` defaults to `date +%Y%m%d`, which is
   `20261007` today. `stage()` skips an existing release dir and then dies at
   `deploy-herdr.sh:99`: "differs from NEW_BIN". This fails safe, because it
   happens before the lock, but the "rerun dry-run" step will fail as
   written. Either remove `~/.local/share/void-workstation/releases/20261007`
   (hard links only; `current` still points to `20260906`) or pass
   `NEW_REL=20261007b` to both `dry-run` and `deploy`.
3. `NEW_BIN=~/.local/share/herdr/staged/herdr-fbd57906 fork/deploy/deploy-herdr.sh dry-run`
   in the same sitting. Expect the capture to cover every live Claude pane
   and the codex pane with no PROBLEM lines. The adversary and implementer
   panes may have closed by then; that is fine.
4. Immediately run `deploy`, detached (`setsid -f ... </dev/null`), from any
   pane. Follow `~/.local/share/claude-accounts/deploy-last/log` from an ssh
   shell, not a pane.
5. Wait for DONE, then reattach. On the codex pane, choose "Trust all and
   continue" once. Check the VERIFY lines and the REPORT lines. If anything
   is wrong, run `deploy-herdr.sh rollback` by hand.

## Residual risks (accepted, none blocks the deploy)

- **Killed by a signal.** The EXIT trap does not run if the deploy itself is
  killed by SIGKILL, or by an untrapped SIGTERM. It is detached and has no
  tty. If that happens, the stub stays and `rollback <run dir>` must be run
  by hand.
- **Rollback refuses.** If `rollback` hits its own `die` (a server still owns
  the socket after 60 s), the trap is already cleared. The log ends with
  that FAIL line rather than "ROLLBACK FAILED". Manual recovery is the same.
- **Real codex and pi end to end** remain untested. The `/proc`-level facts
  from round 1 cover what the deploy depends on. The first restored codex
  sits at the hooks trust dialog until a human answers it.
- **Stale label between relaunches.** Between an agent relaunch and its
  SessionStart, the old label (variant · email) can show briefly. Detection
  re-resolves it.
- **pi label refresh.** pi's label refreshes only on `session_start`,
  `model_select` and `agent_start`. An extension that switches accounts
  without a model change shows the new account on the next turn.
- **Claude hook version.** The installed Claude hook is v7 (the build ships
  v10). It is compatible because it is SessionStart-only and talks to the
  socket directly. Expect an "integration update" notice at most. Reinstall
  it after the deploy, not during.
