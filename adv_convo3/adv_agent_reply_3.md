# Adversarial implementation review — round 3

R1 is settled: the Phase 6 exits bullet now states the early-return mechanism, and
the strengthened clause — scope switches "are not NavigateActions at all" — is
accurate against the code (`control_scope_for_key` returns a `ControlScope`
directly; scope keys never reach `control_action_for_key` or the predicate).
Verified in PLAN.md bytes.

No new findings. Nothing substantive remains.

CONVERGED

Verdict: the landed Phases 0-6b implementation is faithful to its reviewed plan in
every load-bearing mechanism, and after this audit the plan is again an honest
record of the tree. Everything executable was re-executed — full suite 3141/3141
with the pre-existing flake behaving exactly as Phase 0 characterized it,
maintenance scripts, both bun recipes, config round-trips on the tree build, and
the personal config with zero diagnostics — and everything mechanical was read
against the bytes: the reorder paths genuinely mirror the drag paths through
shared classification and guards, the five-layer config plumbing carries all
nineteen new fields, the dispatch/stickiness/exit machinery matches the reviewed
design including its documented divergences, and the docs surfaces agree with the
code and each other. The audit's real yield was the test contract, not the
runtime: one vacuous assertion (the rustfmt-wrapped `j` edit that silently
missed), one untested exit surface, missing event-seam and overlay round-trip
coverage, and four spots of plan/code prose drift — all now fixed with tests that
would actually red if the mechanisms regressed, and with the plan amended by
annotation rather than silent rewrite. The tree is in a state I would trust as the
foundation Phase 7 builds on.
