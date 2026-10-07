Implementer reply to round 3. Both findings verified before accepting.

C1 (BLOCKER) - ACCEPTED, fixed in the script and the plan.
Reproduced your probe exactly (capture with only HERDR_CONFIG_PATH -> 0 panes,
exit 0). My earlier dry runs passed only because I set HERDR_LIVE_SOCKET by
hand; the plan never said so.
- Plan step 5 now passes `HERDR_LIVE_SOCKET=$HERDR_CFG/herdr.sock` explicitly.
- `capture` now takes the server's snapshot as its second argument and derives
  the expected Claude pane set from it (`snapshot_claude_panes`, independent of
  /proc). It exits 1 unless captured set == expected set, naming each missing
  or extra pane; an empty snapshot set is itself a problem.
- `apply`: a pane without a capture entry prints "variant UNKNOWN, session
  <id>, cwd <dir>" plus `<claude-kee|claude-me|claude> --resume <id>`, never a
  plain `claude --resume`.
- Evidence (read-only, scratch copies, recorded as G5 [x]): default socket ->
  exit 1 with PROBLEM lines for all 16 panes; `HERDR_LIVE_SOCKET` set ->
  "captured 16 of 16", exit 0; apply -> 16 patched.

C2 (MAJOR) - ACCEPTED, fixed in the plan.
Agreed: variables chose paths but not the CLI's socket. The Implement preamble
now routes every herdr CLI call and the server start through one wrapper. It
sets `HERDR_SOCKET_PATH=$HERDR_CFG/herdr.sock` and
`XDG_CONFIG_HOME=$(dirname $HERDR_CFG)`, and unsets `HERDR_PANE_ID`. Step 5
ends by asserting that the pid listening on `$HERDR_CFG/herdr.sock` is still
the one saved in step 2. G3 asserts, before its step 6, that this pid is not
the live server's.

Sweep for the same class (a check that passes vacuously on empty input):
- step 10 "every captured pane" is now non-vacuous, because step 5 guarantees
  capture == snapshot set;
- step 2's registry-vs-agent_session comparison iterates live Claude panes;
- G3(a) reads the new server's own environ, which always exists.
