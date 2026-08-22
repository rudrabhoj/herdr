# Adversarial implementation review — round 2

All eight findings are settled. As in the previous engagements I did not take the
acceptance on faith — every claimed fix was re-verified against the tree bytes and
re-executed: `cargo fmt --check` clean, full
`cargo nextest run --locked --no-fail-fast` = **3141/3141 passed** (three more than
round 1's 3138, matching exactly the three claimed new tests).

1. (vacuous spaces sticky test) — `navigation_keys_keep_the_mode_sticky` now
   presses `j` AND `k` in Spaces scope with corrected messages; with two
   workspaces in the fixture both dispatch real switches, so dropping
   Previous/NextWorkspace from the sticky set now reds the suite. Phase 6b bullet
   carries the annotation with the honest root cause. Settled.
2. (entry toggle-off) — `entry_bindings_toggle_off_with_scope_switch_precedence`
   pins both halves: direct-form ctrl+t exits from inside, and with defaults
   `t`/`a` switch scope while `shift+s` toggles off. The Phase 6 design bullet now
   states the precedence. Settled (but see the residual below on an adjacent
   clause in the same bullet).
3. (stale decisions log) — the digit entry now describes the scoped dispatch with
   a supersession note, and "One mode, not three" is marked SUPERSEDED with the
   mechanism half explicitly retained. Settled.
4. (§2.3 prose) — the root-entries mechanism, the reason
   `visible_workspace_order()` was avoided, and the dedup note are all in.
   Settled.
5. (event seams) — TabMoved/WorkspaceMoved assertions landed in the tab-move and
   workspace-move tests via `app.event_hub.events_after(0)`; the Phase 1 bullet
   carries the annotation instead of pretending. Settled.
6. (render/help coverage) — the render test walks all three scopes asserting each
   badge, the `k/j` label, and the absence of `h/l` on vertical bars;
   `scoped_mode_group_lists_live_entries_and_is_filterable` asserts the real
   group, the three live-label entry rows, and filterability. Settled.
7. (overlay round-trip) —
   `local_profile_round_trip_carries_scoped_mode_and_reorder_fields` goes through
   the real `local_keybindings_profile_toml` -> `parse_client_keybindings` seam
   and covers a default field too; §0 and Phase 7 now point at it. Settled.
8. (test count) — Phase 1 verify line reconciled to 6 with the breakdown and the
   conflation source named. Settled.

## Residual

R1. MINOR — the amended Phase 6 exits bullet still contains "sticky predicate
additionally covers scope switches". The predicate does not:
`control_sticky_action` (control.rs:192) lists navigation/reorder/switch actions
only, and scope switches never reach it — `handle_control_key` handles them by
early return (control.rs:34-37) before any dispatch, which is why they keep the
mode. The behavior claim is true; the mechanism claim is false, and it is the
same false-assurance class as finding 2: a Phase 7 implementer told the predicate
covers scope switches will look for entries that do not exist when wiring `p`.
One-clause fix: "scope switches keep the mode by early return in the handler,
before dispatch — they are not (and need not be) in the sticky predicate."

Nothing else remains. Once R1's clause lands I expect to converge.
