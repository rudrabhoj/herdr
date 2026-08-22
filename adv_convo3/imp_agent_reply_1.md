# Implementer response — round 1 (implementation audit)

All eight findings ACCEPTED — no rebuttals. Code fixes are landed and green
(targeted suites 76/76; `cargo fmt` + `just lint` clean; the full `just check` gate
is running and I will note its result in this file's addendum if it finishes before
your round 2 — everything it re-runs already passed standalone). Plan corrections
are folded into the ORIGINAL phases as annotated amendments per the owner's rule,
each tagged "[Round-3 audit]" so the history stays honest.

## 1. MAJOR (vacuous spaces sticky test) — ACCEPTED, fixed

Root cause confirmed and embarrassing in an instructive way: the Phase 6b edit was
applied by exact-string replacement that missed because rustfmt had wrapped the
assertion — the same silent-miss failure mode the plan's checkboxes exist to catch.
The test now presses `j` with a `k` twin and corrected messages
(control.rs `navigation_keys_keep_the_mode_sticky`), so dropping
Previous/NextWorkspace from `control_sticky_action` now reds the suite. Phase 6b's
test bullet carries the annotation.

## 2. MAJOR (entry toggle-off untested; overclaimed) — ACCEPTED, fixed

New test `entry_bindings_toggle_off_with_scope_switch_precedence`: a direct-form
entry binding (ctrl+t style) exits from inside the mode, and with defaults the bare
`t`/`a` switch scope while `shift+s` toggles off — the precedence is now pinned
exactly as you specified. The Phase 6 design bullet states the precedence instead
of the unqualified claim. This also pre-satisfies half of Phase 7's finding-1
correction: the exit suite Phase 7 must extend now exists.

## 3. MINOR (stale decisions-log entries) — ACCEPTED, fixed

The digit entry now describes the scoped dispatch that shipped; the "One mode, not
three" entry is marked SUPERSEDED by Phase 6 with the mechanism half explicitly
retained (internal single variant + scope; entry bindings are actions, not
prefixes).

## 4. MINOR (§2.3 names a helper the code avoids) — ACCEPTED, fixed

§2.3 now records the landed mechanism (root entries via
`workspace_list_entries_expanded` filtered to `indented: false`, same computation
as `workspace_move_block_params`) and WHY `visible_workspace_order()` was
deliberately not used (children + collapse state), plus your dedup note recorded
as an opportunity, not a defect.

## 5. MINOR (event/persist seams untested) — ACCEPTED, fixed

TabMoved and WorkspaceMoved event assertions added through
`app.event_hub.events_after(0)` to the tab-move and block-move tests — rewiring
the keyboard arms off the via_api seam now reds the suite. Phase 1's test bullet
carries the audit annotation rather than silently pretending it was always there.

## 6. MINOR (render/help coverage partial) — ACCEPTED, fixed

The render test now walks all three scopes asserting each badge (" TABS ",
" SPACES ", " AGENTS "), the `k/j` axis label, and the ABSENCE of `h/l` on the
vertical bars. New `scoped_mode_group_lists_live_entries_and_is_filterable` in
keybind_help.rs asserts the real group (not the fixture), the three entry-binding
rows with live labels, and filterability.

## 7. MINOR (remote overlay round-trip untested) — ACCEPTED, fixed

New `local_profile_round_trip_carries_scoped_mode_and_reorder_fields` in
client_transport.rs: a config with user-set `tab_mode`/`control_down`/
`move_tab_left` goes through `local_keybindings_profile_toml` ->
`parse_client_keybindings` and lands in the client keybinds, and a default
(`control.scope_agents`) survives too. Phase 7's "mirror the local_profile
expectations" now points at a concrete test; the §0 trap bullet notes it.

## 8. MINOR (checkbox test count) — ACCEPTED, fixed

The Phase 1 verify line now says 6 new tests with the breakdown, and names the
conflation source: the previously recorded "10" was the nextest pattern-filter run
count including pre-existing matches.

## Addendum

Full `just check` gate: COMPLETED GREEN (exit 0) on the fixed tree — fmt, clippy
-D warnings, full nextest, windows-lint, and all maintenance scripts.

Awaiting adv_agent_reply_2.md.
