Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 fac8aef38bab40de4a7819fb41e886af32542aec788ef71fae06d33671edf812

CONVERGED - no surviving BLOCKER or MAJOR

## Round 2 fixes checked against PLAN.md:1306-1407

- B1: step 5 (1362-1365) now says an install failure is never fatal, is logged, appears in the
  DONE banner with its manual command, and never triggers rollback. G12.3 (1390-1392) injects an
  invalid `hooks.json` and asserts DONE on the new server. Fixed.
- B2: D4 (1322-1325) states the exact expected argv and the deliberate gap from the intent
  record. G12.3 and G12.5 assert that string. Fixed.
- B3: the codex pid poll now runs before the new server starts (1352-1355), and step 10 keeps a
  re-check. Fixed (one clarification below).
- B4: G12.1 (1374-1379) checks that the script and `launch_profile` give the same argv, and that
  1(c) resolves only once per session (1336-1337). Fixed.
- The noted pi-variant regression guard is in D3 (1316-1318).

## Execution order I accept

1. Code 1(a)-(d) with the G12.1 unit tests.
2. Build and stage `herdr-<newsha>`. Re-run the Phase 10 e2e, the migration rehearsal (G12.3,
   including the hidden-codex-pane refusal and the injected install failure) and Phase 11 G3 on
   that binary. Update the Phase 11 binary references.
3. G12.2: stub-based isolated e2e only. No real codex or pi runs against copied credentials (D1).
4. G12.4: Claude angles with throwaway `/tmp/claude-1000/a…` sessions only, each asserted absent
   from the live `agent_session` set and deleted afterwards.
5. Render the codex keep list (step 3) before the Phase 11 capture. The codex capture runs last.
6. Phase 11 `deploy` of `<newsha>`: apply (Claude and codex), then the non-fatal integration
   installs, then the codex-pid poll, then the new server starts. Steps 10-11 follow and DONE
   carries the hook-trust instruction.
7. After DONE, the owner trusts the hooks in `wS:pW`. Then G12.5: files and extensions match the
   backup, `hooks.json` is valid, `hooks.state` holds the herdr hook, and the argv is exactly the D4
   string.

Condition on step 4 of the plan (1353-1354), so the B1 lesson is not undone: if the codex-pid
poll times out, the deploy reports it and continues. It drops that pane's codex `agent_session` and
`agent_resume` from the snapshot and prints the manual `codex resume …` command. It never halts
with no server and never triggers `rollback`. "Reports instead of starting" must not mean
"does not start the new server".

## Residual risks (accepted)

- If the owner picks "Continue without trusting", codex keeps the migration's recorded session.
  In-codex `/new` or `/resume` stays invisible until trust is given.
- Hook trust may need to be given again whenever a herdr reinstall changes the hook handler
  config. What goes into the hash is not visible from strings.
- It is unverified whether codex fires SessionStart at launch or only on the first turn. Nothing
  in the gates depends on it any more: G12.2 uses a synthetic payload, and G12.5 checks trust state,
  not a report.
- macOS, `herdr --remote`, one session used in two accounts at once, an unshared new per-session
  Claude dir, and a variant-less custom `CLAUDE_CONFIG_DIR` (as listed in the plan).
- An npm `codex` update between rehearsal and deploy; the codex version is recorded in the report.
- D5: a reload-config change reaches existing panes only from their next report or detection.
- `herdr-agent-state.ts` as an untracked file in the `~/.pi/agent` git repo; committing it is the
  owner's call.
