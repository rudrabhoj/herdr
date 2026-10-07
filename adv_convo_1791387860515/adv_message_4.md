Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 dd621f3930ec610ec3c78318a53b14e2c0e3393fa79435e76002ccd6b163e25a

# Adversary round 4

CONVERGED - no surviving BLOCKER or MAJOR

## Round-3 fixes, verified

- C1: `migrate-herdr-resume.py capture` now takes the snapshot and derives
  the expected set from it (`snapshot_claude_panes`, `:79-88`; checks
  `:119-131`). Re-ran it read-only on a scratch copy of the live snapshot with
  `HERDR_LIVE_SOCKET` set: `captured 16 of 16`, exit 0. A short or empty
  capture is now a pre-stop abort. Dropped panes print `variant UNKNOWN`
  (`:146`), not a plain `claude --resume`. Plan step 5 passes
  `HERDR_LIVE_SOCKET` explicitly.
- C2: the plan routes every herdr CLI call and the server start through one
  wrapper (`HERDR_SOCKET_PATH`, `XDG_CONFIG_HOME` from `$HERDR_CFG`,
  `HERDR_PANE_ID` unset). Step 5 asserts the socket owner is the step-2 pid,
  and G3 asserts it is not the live pid before its step 6.

## Extra check this round (isolated, cleaned up)

I ran a probe with the staged binary under `/tmp/claude-1000/ahz`
(`env -i`, XDG redirected, no client ever attached). I created one pane,
stopped the server, and added `agent_resume = ["echo","RESUMED-XYZ"]` to the
snapshot. After a restart, the headless server typed and ran it within 6 s.
Step 10 can therefore verify restored Claudes before the owner reattaches,
and an attach after DONE cannot start a second launch of a pending resume.
The probe server is stopped and its directory is deleted.

## Execution order I accept

1. Pre-deploy gates, all on isolated roots: G2 repeat with the operator's real
   launch shape (`setsid -f` from a non-interactive child of a Claude Bash
   tool, stdin `/dev/null`, output to the log); then G3 (a)-(d); then G1
   `dry-run` against the live roots. Nothing stops in G1.
2. Close the review: manifest terminal, watchdog exited, adversary and judge
   panes closed. Run step 2 only after that, so the capture set is stable.
3. `deploy` launched detached, in plan order: 1 stage -> 2 preconditions
   (`relink` on any abort) -> 3 save the old server environ and back up the
   config -> 4 lock stub -> 5 capture last, complete-set and bypass oracles,
   socket-owner check -> 6 stop and copy `session.final.json` -> 7 pane-keyed
   apply -> 8 config plus promote (lock off) -> 9 `env -i` start -> 10 verify
   against the capture -> 11 completions and DONE. Any failure from step 6
   onward runs `rollback`, guarded by no live server, with `relink`,
   `resume_agents_on_restore = false`, and manual commands printed.
4. The owner reattaches only after DONE. G4 runs then.

## Residual risks (accepted, no severity)

- If the deploy rolls back, the owner has to restore accounts and bypass by
  hand. 0.8.0 cannot do it, and the printed commands are the plan for that.
- Livelock instead of damage: a pane can keep `agent_session` in the old
  snapshot after its Claude has exited. A pane can also start Claude after
  the last debounced save. Either one makes step 5 refuse. The owner has to
  close or settle that pane and retry. This is safe, but it can block the
  deploy.
- Panes are judged correct at capture time. If an owner or agent relaunches a
  pane in a different variant between step 5 and step 6, it restores with the
  captured variant. The window is seconds, and the lock is already in place.
- Step 10's "fresh shell pane" creates a pane in the owner's real layout. The
  script should close it before DONE.
- The Claude hook stays at integration v7 while the new binary ships v10.
  Reporting works, but expect an "outdated integration" badge. Reinstalling
  it is a separate decision for the owner.
- `startup_per_agent_delay` spaces the 16 resumes. Step 10 must poll until
  every captured pane has its process, not take one snapshot.
- The Phase 11 heading still reads `[UNHARDENED]`. Updating it belongs to the
  implementer or the judge, not to me.
