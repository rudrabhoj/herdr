Implementer reply to round 2. All four accepted.

B1 MAJOR - ACCEPTED. Step 5 now says an integration install failure is never
fatal: it is logged, listed in the DONE banner with its manual
`herdr integration install <x>` command, and never triggers `rollback`.
G12.3 adds the injected failure (an invalid pre-existing `hooks.json` in the
isolated CODEX_HOME) and asserts the deploy still reaches DONE on the new
server.

B2 MINOR - ACCEPTED. D4 now states the exact expected restored argv,
`codex resume -m gpt-6-astra --search --dangerously-bypass-approvals-and-sandbox <id>`,
and says it differs from the intent record's quoted live command by design,
because effort comes from config.toml. G12.3 and G12.5 assert that exact
string.

B3 MINOR - ACCEPTED. Polling for the captured codex pids to be gone (with a
reporting timeout) now happens just before the new server starts; step 10
keeps a re-check.

B4 MINOR - ACCEPTED.
- G12.1: `launch_profile` on the live codex argv shape returns exactly the D4
  string, and the migration script's capture of the same argv returns the
  identical argv, so the first detection after restore re-derives the same
  command and never rewrites it.
- 1(c) resolves once per newly established session; G12.1 asserts a second
  report for the same session does not re-resolve.

Your noted non-finding: added to D3 ("a future pi `agent_variant` must not
replace a self-reported resume").
