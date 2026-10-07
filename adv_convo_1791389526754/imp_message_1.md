Implementer reply to round 1. Phase 12 rewritten. Before accepting, I re-checked these
claims myself:
- A1: `~/.local/bin/pi` execs node, `cli.js:11` sets `process.title`, and a
  `node -e 'process.title="pi"' -- --model x` probe leaves the cmdline as `pi` plus NULs.
- A2: the codex binary contains the "Hooks need review" / "Continue without trusting"
  strings.
- A5: `git log e897ed0e..HEAD -- src` is empty.
- A9: `~/.codex/config.toml` already pins model, effort, approval and sandbox.

A1 MAJOR - ACCEPTED. D3: the fork's pi asset reports `resume_argv` itself,
built from `process.argv` with its own allowlist
(`--model`/`--thinking`/`--provider`/`--approve`/`-a`) plus `--session <path>`.
There is no `resume_keep_args.pi`, so the server resolver returns early for pi
and never overwrites the reported command. G12.2's pi stub sets
`process.title="pi"`.

A2 MAJOR - ACCEPTED.
- D2: the owner trusts once, interactively, on the first codex start after
  install; the DONE banner says so (step 5).
- `--dangerously-bypass-hook-trust` is explicitly not used without an owner
  ruling.
- G12.5 checks `hooks.state` for the herdr hook after trust.
- "Continue without trusting" is a stated residual.

A3 MAJOR - ACCEPTED. D1: no real codex or pi ever runs against copied
credentials. G12.2 is built exactly on your stub design. The live check after
install is file-level only (extensions byte-identical to the backup,
`hooks.json` valid).

A4 MAJOR - ACCEPTED (step 4).
- The expected codex set comes from the live server: `herdr pane list` with
  `agent == "codex"`.
- Each pane must have exactly one rollout fd and one writer-lock fd with
  matching uuids; the uuid is taken from the lock name.
- Codex capture runs last. Apply adds `agent_session` + `agent_resume`.
- The report and rollback print `codex resume <kept> <id>` with the cwd.
- G12.3 includes a hidden-pane refusal case.

A5 MAJOR - ACCEPTED. There is now one explicit order:
1. code changes 1(a)-(d);
2. build and stage `herdr-<newsha>`;
3. re-run the Phase 10 e2e, the migration rehearsal and G3 on that binary;
4. Phase 11 deploys `<newsha>`;
5. the codex keep list is rendered before capture;
6. integrations are installed inside the deploy, after apply and before the
   new server starts. The restored codex is tracked from its first start (after
   the trust modal).

A6 MAJOR - ACCEPTED. Step 6 / G12.4 use only throwaway sessions under a
`/tmp/claude-1000/a...` cwd, assert they are absent from the live
`agent_session` set, and delete them afterwards.

A7 MINOR - ACCEPTED as documented behaviour (D5): a changed resolution applies
from each pane's next report or detection onward.

A8 MINOR - ACCEPTED, code change 1(c): resolution runs when a state report
first establishes a session. G12.1 covers it.

A9 MINOR - ACCEPTED (D4): `-c`/`--config` are not kept, and the owner's
overrides are already in config.toml. `--worktree` and `--remote` are never
kept.

A10 MINOR - ACCEPTED: the keep list gains `--add-dir=`, `-C=`, `--cd=`,
`--enable=`, `--disable=` and `--no-alt-screen`; pi's `--approve`/`-a` sit in
the D3 allowlist; the untracked-file note for `~/.pi/agent` is in step 5.

Residuals: the old-codex-pid check and `codex --version` recording are now in
step 4.
