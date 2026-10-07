Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 2c6cfc129098960a35918089f7a35ffa83f6aa89bbb77b6aec9d81dd7c721fe9

# Adversary round 2

## Round-1 fixes, verified in the artifacts

- A1 fixed. `herdr.config.toml:100` keeps `"--permission-mode="`. Re-ran the
  rewritten `capture` read-only against a rendered copy: exit 0, 11 panes now
  `claude-kee --permission-mode bypassPermissions --resume <id>`, wY:p1/wY:p3
  keep `--dangerously-skip-permissions`, wV:p1/wS:pT/wY:p2 have none. The
  `bypass()` oracle (`migrate-herdr-resume.py:72-76`) reads raw argv in both
  forms and is independent of the keep list.
- A3 fixed. Applied that capture to a scratch copy of the live `session.json`:
  16 patched. Cross-checked independently (live pid -> registry sid -> the
  patched pane carrying that sid): all 16 argv and config dirs are the right
  ones, so the `public_pane_numbers` + alphabet mapping is correct on real
  data. Unmatched Claude panes lose `agent_session` (`:126-131`).
- A2 fixed in the plan (C6, steps 3/9/10; rollback uses the same env). The new
  server's session/socket dir is `config_dir()` (`src/session.rs:163-169`), so
  an `env -i` start with the old env still finds `~/.config/herdr/session.json`.
- A4 fixed in the plan (lock stub at step 4, step 10 asserts new pid + 0.9.3,
  DONE gate). A5/A6 fixed in the plan text. A7 accepted as answered.

`deploy-herdr.sh` does not exist yet, so everything below is about the plan
text the script will be written from.

### B1(r2) - MAJOR, VERIFIED. The lock stub survives every rollback that runs before step 8, so the owner is left with a `herdr` that only says "wait for DONE"

Plan: PLAN.md:1141-1142 (step 4 stub), 1147 ("every failure runs rollback"),
1154-1156 (step 8 promote "restores the real symlink"), 1173 (rollback
"Switch `current` back ... (restores `~/.local/bin/herdr`)"), 1189-1191 (G3).

Evidence:
- Step 4 replaces the FILE `~/.local/bin/herdr` (today a symlink to
  `.../current/bin/herdr`) with a regular-file stub. Switching `current` only
  retargets `void-workstation/current`; it cannot touch a regular file at
  `~/.local/bin/herdr`. Only the promote logic re-creates that symlink
  (`promote.sh:19-26`).
- Rollback is automatic from step 6 on, i.e. also when step 6 (stop timeout,
  pid never exits) or step 7 (apply raises) fails - both BEFORE step 8.
  Rollback's text claims the `current` switch restores `~/.local/bin/herdr`,
  which is false in exactly those cases.
- The existing promote logic treats a non-symlink at `~/.local/bin/herdr` as a
  pre-promotion binary: `promote.sh:20-23` moves it to
  `backups/herdr-before-promotion` (`test ! -e` first, under `set -e`). A
  generalized promote built from it archives the stub as the "pre-promotion
  herdr", and the next promote that meets a stub again aborts at
  `test ! -e` after `current` was already switched (line 12 runs first).
- G3 rehearses `deploy` then `rollback`, i.e. rollback after step 8 has
  already replaced the stub. No gate runs a rollback with the stub in place.

Failure: stop hangs at step 6 -> rollback starts 0.8.0 with the saved env and
prints manual commands -> the owner types `herdr` -> stub: "herdr upgrade in
progress - wait for DONE", forever. The owner is told no working command and
the only working binary is an absolute release path nobody mentioned. This is
the "must never break my installed herdr" ruling.

Required: rollback (and every pre-stop abort) re-creates the
`~/.local/bin/herdr -> .../current/bin/herdr` symlink explicitly and
atomically (`ln -s` + `mv -T`) whatever it finds there; the generalized promote
recognizes the stub (e.g. a marker line) and replaces it without archiving;
G3 adds a rollback injected at step 7 (stub present) and asserts
`readlink ~/.local/bin/herdr` and that `herdr --version` prints 0.8.0.

### B2(r2) - MAJOR, PLAUSIBLE. G3 runs the deploy script "on an isolated copy", but the script's targets are the live paths, and the rehearsal env would hide the A2 fix

Plan: PLAN.md:1126-1127 ("every herdr call by absolute path"), 1129-1158
(steps name `~/.local/bin/herdr`, `releases/`, `current`,
`~/.config/herdr/...`, `~/.config/herdr/herdr.sock`), 1189-1191 (G3:
"isolated copy (fake session ids, every `HERDR_*` unset), run `deploy` then
`rollback`").

Evidence: the plan defines the script only in terms of live locations, and
G3 says to run that same script's `deploy`. `deploy` installs the stub on
`~/.local/bin/herdr` (step 4), runs `herdr server stop` against the socket it
resolves (step 6), promotes `void-workstation/current` (step 8). Nothing in the
plan says these roots are parameters, or that G3 points them at the
isolated tree. Separately: the prior e2e rehearsals stripped
`CLAUDE_CONFIG_DIR` before starting anything (`tests/e2e_migration.py:20-21`,
`tests/e2e_variants.py:21-22`). If G3 does the same, the step-9
`env -i <saved env>` fix is never exercised: a missing `env -i` would also pass.

Failure (the costly one): G3 "rehearsal" swaps the live `current` to
`releases/20261007`, installs the stub over the live `~/.local/bin/herdr`, or
stops the live server if `HERDR_SOCKET_PATH` resolution falls back to the
default socket - an unplanned live deploy with no capture. (The cheaper one: G3
green while step 9 still leaks the operator's `CLAUDE_CONFIG_DIR`.)

Required: every root the script touches (bin dir, void-workstation base,
herdr config dir, socket, claude-accounts dir) is a variable with the live
value as default, and G3 sets all of them under `/tmp/claude-1000/a<short>`;
G3 records `readlink` of the live `~/.local/bin/herdr` and `current` plus the
live server pid before and after and fails if any changed; G3 runs with the
operator's real `CLAUDE_*` env present (only `HERDR_*` redirected) and asserts
the rehearsal's restored plain-claude pane has no `CLAUDE_CONFIG_DIR`.

### B3(r2) - MINOR, PLAUSIBLE. Rollback can start a second server

Plan: PLAN.md:1147-1149, 1166, 1176.

Evidence: rollback triggers include "stop did not finish" (step 6) and
"server-level failure" at step 10, which covers "a server is listening but it
is not the new pid / not 0.9.3" (A4's own case). Rollback then starts 0.8.0
unconditionally.

Failure: two servers race for `~/.config/herdr/herdr.sock` and both rewrite
`session.json`; or rollback reports success while the wrong server keeps
serving. Required: rollback first establishes that no herdr server is alive
(old pid gone, nothing listening on the socket; stop the stray one with its
own binary), and refuses to start 0.8.0 otherwise, printing why.

## Sound (checked this round)

- Pane-keyed capture/apply on real data (16/16, cross-checked above).
- Bypass oracle catches the A1 class: a keep list missing either form now
  fails `capture` before anything stops.
- Old server env keys (`/proc/4222/environ`) contain no `XDG_*` and no
  `HERDR_SOCKET_PATH`, so `env -i` with them lands on the same config dir and
  socket the live server uses.

## Residual (no severity)

- `loop_watchdog.sh` for this conversation drives `herdr` until the manifest
  is terminal; it ends on convergence, but step 2 should name "no review
  automation still running" alongside closing the adversary pane, since a
  late nudge would be typed into a restored Claude pane.
