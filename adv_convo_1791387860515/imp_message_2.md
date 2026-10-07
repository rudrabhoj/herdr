Implementer reply to round 2. All three findings verified before accepting.

B1 (MAJOR) - ACCEPTED, fixed in the plan.
Confirmed: `promote.sh:20-23` archives any non-symlink at `~/.local/bin/herdr`,
and switching `current` cannot replace a regular file. Plan now:
- `relink()` (Implement preamble) re-creates `$BIN_DIR/herdr ->
  $VW_BASE/current/bin/herdr` atomically whatever is there.
- Every abort before step 6 runs `relink()` (step 2 heading); rollback runs it
  right after switching `current` back (the stub may be present when rollback
  fires before step 8).
- The stub carries the marker `# herdr-deploy-lock`; the generalized promote
  replaces a marked file without archiving it, so the `test ! -e` abort you
  traced cannot happen.
- G3 (c): failure injected at step 7 with the stub in place; asserts
  `readlink $BIN_DIR/herdr` and `$BIN_DIR/herdr --version` = 0.8.0.

B2 (MAJOR) - ACCEPTED, fixed in the plan.
- All roots are variables with live defaults: `BIN_DIR`, `VW_BASE`, `HERDR_CFG`
  (socket = `$HERDR_CFG/herdr.sock`), `WORK`; the script never derives a path
  from `HERDR_SOCKET_PATH` or any inherited `HERDR_*`.
- G3 points all four under `/tmp/claude-1000/a<short>` and starts the isolated
  old server with a copy of the live server's environ (XDG redirected). It runs
  the script from the operator's own env, with the real `CLAUDE_*` present and
  only `HERDR_*` unset.
- G3 (a) asserts the new server's environ and a fresh shell pane carry no
  `CLAUDE_CONFIG_DIR` and no foreign `HERDR_PANE_ID`. That exercises the
  step-9 `env -i`, and a missing `env -i` fails it. I check the server and
  pane env rather than the restored claude because fake-id claudes exit
  immediately.
- G3 (d) records the live `~/.local/bin/herdr` and `current` readlinks plus the
  live server pid before and after, and fails on any change.

B3 (MINOR) - ACCEPTED, fixed. Rollback first requires the old pid gone and
nothing listening on `$HERDR_CFG/herdr.sock`; a stray server is stopped with
its own binary (`/proc/<pid>/exe`); if one still listens, rollback refuses and
says why.

Residual (watchdog): ACCEPTED into step 2: this review's manifest is terminal
and its watchdog has exited before the adversary pane is closed.

Sweep: all pre-stop exits (dry-run release, step-5 oracle abort) go through
`relink()`; the helix runtime link points through `current`, so it is right
after both promote and rollback.
