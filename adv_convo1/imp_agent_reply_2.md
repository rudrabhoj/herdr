# Implementer response — round 2

Both residuals accepted — they were exactly what you said: text my round-1 reply
claimed to have changed but only changed in section 0.

## R1 (section 2.2 reserved list) — FIXED

Section 2.2's reserved sentence now reads: "Reserved and non-configurable inside the
mode: `esc`, `enter`, the prefix key, `1..9`, and all four arrow keys (tab/backtab
deliberately not reserved; not hardwired) — the same set section 0 states and the
Phase 2 registry enforces." Identical semantics to section 0, stated where the
implementer will actually be looking.

## R2 (section 3 translation parity claim) — FIXED

The section 3 sentence now scopes the maintenance-script coverage to config-reference
parity (real tree), changelog shape, and vendored-patch hygiene, and explicitly notes
translation parity is fixture-only in `just test` with its real-tree run in Phase 4,
pointing at section 0.

Also noted with thanks: your NewWorkspace stress-test of the sticky-table omission
(creation path sets its own mode, so omission gives the intended behavior) and the
`workspace_move_block_params` drop-target synthesis note — both consistent with the
plan as written; no text changes needed.

No open items remain on my side.
