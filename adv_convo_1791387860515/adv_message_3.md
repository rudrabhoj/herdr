Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 b8c16ff8305151069a0e8650d0991320ebae1534f6f2c884be3d9b3dfe257973

# Adversary round 3

## Round-2 fixes, verified in the plan text

- B1: `relink()` defined (PLAN.md Implement preamble), run on every pre-stop
  abort (step 2 heading) and in rollback after the `current` switch; marked
  stub replaced without archiving; G3(c) injects a step-7 failure with the
  stub present. Accepted.
- B2: roots are variables with live defaults; G3 puts them under /tmp, runs
  with the real `CLAUDE_*`, asserts server/pane env (a), and checks live
  readlinks + pid (d). Accepted as far as it goes; see C2 for the part it
  misses.
- B3: rollback requires no live server and refuses otherwise. Accepted.
- Watchdog residual folded into step 2. Accepted.

### C1(r3) - BLOCKER, VERIFIED. Step 5 as written captures zero panes and exits 0; apply then strips every Claude pane's resume and prints wrong-account commands

Plan: PLAN.md step 1 ("Render the new config ... to the deploy dir"), step 5
("`migrate-herdr-resume.py capture` keyed by pane id with the rendered new
config"), step 7 (unmatched pane "loses its `agent_session` ... manual command
is printed"), step 10 ("every captured pane ...").

Evidence:
- `migrate-herdr-resume.py:30-31`: `CONFIG = HERDR_CONFIG_PATH or ...`;
  `:83`: `live_socket = os.environ.get("HERDR_LIVE_SOCKET", str(CONFIG.parent / "herdr.sock"))`.
  With the rendered config in the deploy dir, the default socket is
  `<deploy dir>/herdr.sock`, which no Claude process has as
  `HERDR_SOCKET_PATH`. The plan never mentions `HERDR_LIVE_SOCKET`.
- Probe (read-only, scratch copies): rendered config copied to
  `scratchpad/deploy-x/config.toml`, `capture` run with only
  `HERDR_CONFIG_PATH` set ->
  `captured 0 claude panes`, `exit=0` (no PROBLEM lines: the bypass oracle
  has nothing to compare). `apply` on a copy of the live snapshot ->
  `patched 0 claude panes`, then `NOT RESUMED (run by hand): wS:p1: claude --resume <sid>`
  for every pane, `exit=0`.
- Nothing downstream notices: step 10 checks "every captured pane" (vacuous
  over an empty capture). Only G4's "this session resumed in `wY:p1`" fails,
  after every process is gone.

Failure: the deploy "succeeds", all 16 Claude panes come back as bare shells,
and the DONE banner hands the owner 16 commands of the form
`claude --resume <id>` - personal account, no bypass - for panes that were
`claude-kee` with bypass. Following the plan's own recovery instructions
produces the exact C2 outcome. (The same hole fires for any other reason the
capture comes back short: a socket path that differs by a trailing slash, a
`comm` rename in a Claude update, an `environ` read refused.)

Required:
1. The script passes `HERDR_LIVE_SOCKET=$HERDR_CFG/herdr.sock` to `capture`
   explicitly (stated in the plan).
2. `capture` takes the expected pane set (the live Claude panes from step 2,
   i.e. the server's `agent_session` list) and exits non-zero unless the
   captured set equals it - never accept an empty or short capture before
   the stop.
3. `apply`'s dropped-pane line must not present `claude --resume <id>` as the
   command to run; with no capture entry the variant is unknown, so print that
   (and the cwd) rather than a confident wrong-account command.

### C2(r3) - MAJOR, PLAUSIBLE. In G3 the herdr CLI calls still resolve to the LIVE socket; the rehearsal's step 6 can stop the live server

Plan: Implement preamble ("The script never derives a path from
`HERDR_SOCKET_PATH` or any inherited `HERDR_*`"; "every herdr call by absolute
path"), step 6 (`herdr server stop`), G3 ("only `HERDR_*` unset", (d) checks
live pid "before and after").

Evidence: the variables say where the script looks, not where the herdr CLI
connects. The CLI resolves its socket from `HERDR_SOCKET_PATH`, else
`config_dir()/herdr.sock`, where `config_dir()` is `XDG_CONFIG_HOME/herdr` or
the platform default `~/.config/herdr` (`src/config/io.rs:30-35`,
`src/api/mod.rs:91-93`, `src/session.rs:163-173`). G3 unsets `HERDR_*` and
the operator env has no `XDG_CONFIG_HOME`, so every `herdr pane get`,
`herdr server stop`, `herdr status` the script issues in G3 talks to
`~/.config/herdr/herdr.sock` - the live server - unless the script itself sets
the socket for each call. G3(d) only detects the live pid change after the
fact.

Failure: running G3 executes step 6 `server stop` against the live server: all
16 Claude panes die with no capture applied to the live snapshot; the next
`herdr` restores them through 0.8.0 as `claude --resume` (C2) - an unplanned
live deploy without the migration. Less dramatic variants: step-2
preconditions compare the isolated fake-id snapshot against live panes and
abort, so G3 never reaches the code it is meant to rehearse.

Required: the plan states that every herdr CLI invocation and the server start
in the script run with `HERDR_SOCKET_PATH=$HERDR_CFG/herdr.sock` and
`XDG_CONFIG_HOME=$(dirname "$HERDR_CFG")` set explicitly (and `HERDR_PANE_ID`
unset), and that before step 6 the script asserts the pid listening on
`$HERDR_CFG/herdr.sock` is the pid saved in step 2; G3 additionally asserts,
before its step 6, that this pid is not the live server's.

## Sound (this round)

- `relink()` + marker stub close the B1 path; rollback's no-live-server guard
  closes B3.
- G3(a) checks the new server's own `/proc/<pid>/environ`, which does detect a
  missing `env -i` even though fake-id Claudes exit immediately.
