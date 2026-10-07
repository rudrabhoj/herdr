Reviewed: /home/rudrabhoj/Dev/herdr_and_claude/herdr/PLAN.md sha256 eef4936d18d17cf5bac1934db3d6d6cac929039781f68142aec9ca4380bca138

# Round 2

## Fixes checked against the plan (PLAN.md:1273-1388) and the artifacts

- **A1 fixed.** D3 (1312-1316) and code change 1(d) make the pi asset send `resume_argv`. With
  no `resume_keep_args.pi` and no pi variant, `resolve_agent_launch` returns early
  (panes.rs:1665-1671). A report that carries `resume_argv` also skips resolution
  (panes.rs:1633), so the server never overwrites pi's own command. G12.2's stub reproduces the
  /proc wipe. Accepted.
- **A2 fixed.** D2, step 5 banner, G12.5 `hooks.state` check, and a stated residual. Accepted.
- **A3 fixed.** D1 plus the stub design in G12.2. The live check is file-level. Accepted.
- **A4 fixed.** The expected set comes from the live server, uuids must match across the two fds,
  the capture runs last, there is a hidden-pane refusal case, and the report and rollback print
  the manual command. Accepted. One placement problem remains (B3 below).
- **A5 fixed.** The order is explicit (1324-1352). The new sha replaces e897ed0e and the Phase
  10/11 gates are re-run on it. Accepted.
- **A6 fixed.** Step 6 sessions are throwaway, asserted absent, and deleted. Accepted.
- **A7-A10.** D5, 1(c), D4 and the keep-list or allowlist changes. Accepted. Small follow-ups
  are in B2 and B4.

## New findings

### B1(r2) - MAJOR, PLAUSIBLE. Installing the integrations sits inside Phase 11's "rollback on any failure from step 6" window, and the plan does not say an install failure is non-fatal

**Plan**: PLAN.md:1346-1349 (step 5: "inside the Phase 11 deploy after apply and before the new
server starts"). Phase 11 Accepted execution order: "`deploy` detached, steps 1-11, `rollback` on
any failure from step 6". Phase 11 step 10: "not a rollback: rolling back loses every variant".
R1: rollback leaves accounts and bypass to the owner.

**Evidence**: `herdr integration install` is purely local (src/cli/integration.rs:89-97 calls
`crate::integration::install_target`). It can fail on its own, for example on a parse error of an
existing hooks.json (targets.rs:174-178), the hard-link refusal and the non-regular-file refusal
(config_file.rs:27-69), or the pi "extension directory not found" error (targets.rs:67-78).
Today `~/.codex/config.toml` has link count 1 and mode 600, and hooks.json is absent, so the
likely case is fine. The risk is that the step inherits the deploy's fail-fast rule.

**Failure**: any non-zero exit from either install, after the old server has stopped, sends the
deploy into `rollback`. 0.8.0 comes back with `resume_agents_on_restore = false`. All 16 Claude
panes lose their variant and bypass and have to be restored by hand from printed commands. A
non-essential step (codex tracking would otherwise start at the next codex launch) then destroys
the essential one.

**Required**: one sentence in step 5. Each integration install failure is logged, reported in the
DONE banner with the manual `herdr integration install <x>` command, and never triggers
`rollback`. G3's rehearsal should inject one install failure, for example with a pre-existing
invalid `hooks.json` in the isolated CODEX_HOME, and assert that the deploy still reaches DONE on
the new server.

### B2(r2) - MINOR, VERIFIED. G12.5's "resumed with its flags" is no longer the live flag set; state the exact expected argv

The live argv is `-m gpt-6-astra -c model_reasoning_effort=high --search --dangerously-bypass-approvals-and-sandbox`.
Under D4, `-c` is dropped, which is sound because config.toml:2 pins
`model_reasoning_effort = "high"`. So the expected restored argv is
`codex resume -m gpt-6-astra --search --dangerously-bypass-approvals-and-sandbox <id>`. G12.5 and
step 10 should assert exactly that string, and note under D4 that this argv differs from the
intent record's quoted command by design. Otherwise a checker comparing against the live argv
will either fail or be loosened to "contains the bypass".

### B3(r2) - MINOR, PLAUSIBLE. The "old codex pids are gone" check runs too late

PLAN.md:1344-1345 puts it in step 10, after the new server has already typed `codex resume`
into the restored pane. The writer-lock collision it guards against happens at restore time. Move
the check to just before the new server starts: poll until the captured codex pids are gone,
time out and report. Keep step 10's re-check.

### B4(r2) - MINOR, PLAUSIBLE. Two cross-checks the gates leave open

- G12.3 checks that the codex pane gets `agent_resume` but not that the script's argv equals what
  the server will re-derive. After restore, `resolve_detected_agent_launch` (panes.rs:1712-1738)
  recomputes it with `launch_profile`, so a mismatch in flag order or placement between
  `migrate-herdr-resume.py` and code change 1(a) silently rewrites the saved command on first
  detection. Assert equality on the live codex argv shape.
- 1(c) must run once per newly established session, not per state report. `UserPromptSubmit`/`Stop`
  arrive every turn and resolution reads /proc (the multiplicative path rule in CLAUDE.md). Add
  "second report does not re-resolve" to G12.1.

## Not a finding, noted

If an owner later adds a pi `agent_variant`, `resolve_agent_launch` would no longer return early
for pi. It would compute `<variant> --session <path>` from the wiped `["pi"]` argv and
`set_launch_resume` would overwrite pi's self-reported flags. This does not apply today, since D3
says no pi keep list and no pi variant. A one-line note in D3 ("a pi variant must keep the
reported resume") would stop a future regression.
