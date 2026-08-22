# Adversarial implementation review of Phases 0-6b — round 1

Scope: the landed patch series (uncommitted tree on `10974c82`: 16 modified files +
`src/app/input/control.rs`) audited against PLAN.md Phases 0-6b on four fronts:
conformance, correctness, docs surfaces, personal config. Every executable claim was
re-run; every code claim was checked against the diff and surrounding tree.
rust-analyzer again served stale positions for the recently edited navigate.rs
(findReferences pointed into the binding table); disputed anchors below were
confirmed against file bytes.

## Claims re-verified as TRUE (so we do not re-litigate)

- **Test gates**: `cargo nextest run --locked --no-fail-fast` = **3138/3138 passed**
  (1 leaky, pre-existing). A first fail-fast run reproduced exactly the Phase 0
  flake (`inactive_owner_cancels_idle_stream_and_dispatches_close`, Timeout under
  parallel load) and it passes in isolation, precisely as the Phase 0 checkbox
  characterizes. Maintenance unittest suite: 98/98. `config_reference_check.py` and
  `docs_translation_parity.py --docs-root docs/next/website/src/content/docs` both
  pass standalone. Both bun recipes pass (integration-assets 15+4, plugin-marketplace
  31). Toolchain present as Phase 0 claims (just 1.58.0, nextest 0.9.143, bun 1.3.14).
- **Config plumbing**: all 19 new fields (3 mode entries, 12 `control_*`, 4 reorder)
  are wired through every one of the five layers — `KeysConfig` with doc comments,
  `KeysConfigOverlay`, `apply_field!`, `Default`, `local_profile` — checked
  field-by-field. Reserved set landed exactly as specified: prefix combo reserved at
  the registry callsite, esc/enter/all-four-arrows/1..9 in
  `reserve_control_runtime_keys` (keybinds.rs), tab/backtab deliberately not
  reserved. Prefix-syntax rejection and reserved-key conflicts diagnose as tested.
- **Reorder correctness**: `move_workspace_in_root_order` (navigate.rs) mirrors the
  mouse drop path (mouse.rs:849-872) literally — same block classification, same
  insert-index derivation. Linked-worktree refusal is enforced in the shared
  `workspace_move_block_params` (sidebar.rs:389-394), matching the drag-start guard
  (mouse.rs:686-689), so keyboard and drag refuse identically, including the
  orphaned-linked-worktree edge. `Workspace::move_tab` (workspace.rs:637) has
  exactly the §2.3 gap-index semantics (`i+1` recomputes to source and no-ops;
  active tab re-derived by root pane); `focused_tab_move` returns None at both
  edges so no API call is made. Tab verbs consistently act on `state.active`
  (matching `next_tab`/`previous_tab`).
- **Mode machinery**: dispatch order (modifier skip → prefix chains into Prefix →
  scope switch → esc/enter/entry-toggle → verbs → hardwired arrows → inert),
  sticky predicate + restore-if-Terminal, `leave_command_mode` exits (incl. the
  Copy branch), exhaustive per-scope verb matches, axis-split with inert off-axis
  pairs, global arrows. Registration complete: `handle_key` arm, headless arm,
  `unreachable!` list, ascii-classification test row, `wants_ascii_input`, absent
  from `mouse_motion_changes_view`, `mode_bar_covers_tab_row` + extended regression
  test, ui.rs render arm. `modal_paste_target_active` needs no arm (falls to
  `false`) — correctly untouched. Mobile entry (`mobile_switcher_scroll = 0`,
  `Mode::Navigate`) matches the WorkspacePicker arm exactly. The pure-state
  `execute_navigate_action_in_context` duplicate is test-only scaffolding
  (`handle_navigate_key` is `#[cfg(test)]`), so no production event-emission gap.
- **Docs surfaces**: config-reference entries match the model doc comments;
  DEFAULT_CONFIG carries all 12 `control_*` + 3 mode + 4 reorder keys and the
  template round-trips clean through the tree-built `herdr config check`; the
  en/ja/zh-cn paragraphs are content-parallel; the en-only `tab_bar_position`
  sentence edit is fine because the ja/zh docs never carried that sentence;
  changelog entries staged in docs/next only. Bars and help overlay use live
  `keybind_label`s for every configurable key and hardwired text only for reserved
  keys; "unset" labels for the unbound reorder entries match existing convention.
- **Personal config and environment claims**: `herdr config check` = ok on both the
  installed binary and the tree build, zero diagnostics; contents match the Phase
  5/6b record (ctrl+t/ctrl+o/ctrl+g, `toggle_sidebar = ["prefix+b","ctrl+s"]`,
  alt+i/o, `last_pane = "prefix+p"`). Zellij config: Ctrl t→tab (179), Ctrl
  o→session (160), Ctrl g→locked (150), Ctrl s→scroll (176), Ctrl p→pane (182) —
  every sacrifice argument holds. skhdrc: all chords cmd-based (non-cmd lines are
  device/mode declarations only). fisher: only fisher + nvm.fish, so the fzf.fish
  claim holds. `.git/info/exclude` matches Phase 0. `PROTOCOL_VERSION` untouched at
  20, matching the Phase 5 log and the no-bump guardrail. The personal direct
  entry bindings (ctrl+t/o/g) do reach `control_entry_binding_matches` and toggle
  off (verified by dispatch-order reading; see finding 2 for the missing test).

Now the findings.

---

## 1. MAJOR — Phase 6b claims "the spaces sticky test moved to `j`"; the landed test still presses `l`, making the assertion vacuous

**Plan text** (Phase 6b, Tests): "the spaces sticky test moved to `j`."

**Code evidence**: `navigation_keys_keep_the_mode_sticky` (control.rs:368-374):

    app.state.control_scope = ControlScope::Spaces;
    app.handle_control_key(plain(KeyCode::Char('l')));
    assert_eq!(app.state.mode, Mode::Control, "workspace switch stays in mode");

After the axis split, `l` is INERT in Spaces scope (`control_action_for_key`
returns None, control.rs:139-144), so the key dispatches nothing and the mode
trivially stays Control. The assertion passes without exercising what its message
claims. No test anywhere drives workspace navigation through `handle_control_key`
in Spaces scope: the shared-verb table checks `control_action_for_key` mapping only
(no dispatch), and the adversarial walk asserts invariants, not mode. The full
sticky round-trip (`j`/`k` → Previous/NextWorkspace → `leave_navigate_mode` →
Terminal → restore) is covered in Tabs scope only.

**Failure scenario**: dropping `PreviousWorkspace`/`NextWorkspace` from
`control_sticky_action` (control.rs:192) passes the entire suite; users would be
dumped to Terminal on every k/j in SPACES mode with zero red tests.

**Correction**: change the pressed key to `j` (as Phase 6b claims) and ideally add
the `k` twin; reopen the Phase 6b test bullet until the edit actually lands. Also
fix the stale assertion message.

## 2. MAJOR (test adequacy) — the entry-binding toggle-off exit has zero test coverage, and the Phase 6 design bullet overclaims it

**Plan text** (Phase 6 design): "Exits and stickiness unchanged: esc/enter leave,
the entry bindings toggle off, prefix chains into prefix mode..."

**Code evidence**: `control_entry_binding_matches` (control.rs:66) is exercised by
no test: `exit_keys_leave_and_prefix_chains_into_prefix_mode` covers esc, enter,
and the prefix chain only. Worse, the unqualified "the entry bindings toggle off"
is false for two of the three defaults: `handle_control_key` checks scope switches
BEFORE the entry toggle (control.rs:30-37, documented only in the code comment), so
with defaults the bare `t` (tab_mode rhs) and `a` (agent_mode rhs) are captured as
scope switches and never toggle off — only `shift+s` actually exits. The personal
config's ctrl+t/ctrl+o/ctrl+g exits ride this untested function. This is the same
plain-array surface engagement 2 flagged for Phase 7 as "the one no compiler error
covers"; the hole already exists for the three implemented modes.

**Failure scenario**: removing `agent_mode` from the array (or a Phase 7 rebase
dropping a line) passes the whole suite; the mode's own binding becomes inert
inside the mode, and manual testing misses it because esc still works.

**Correction**: add the toggle-off rows now: (a) a direct-form entry binding
(e.g. `tab_mode = "ctrl+t"`) pressed inside the mode exits via
`leave_command_mode`; (b) with defaults, `shift+s` exits while `t`/`a` switch
scope — pinning the precedence. Amend the Phase 6 design bullet to state the
scope-switch-over-toggle precedence instead of the unqualified claim.

## 3. MINOR — the decisions-log digit entry contradicts the implemented and documented behavior

**Plan text** (decisions log): "`switch_workspace`-style indexed bindings inside
control mode: only `1..9` for tabs, reserved and hardwired; workspace indexing
stays on the global `switch_workspace` binding to keep the mode keymap small."

**Code evidence**: `control_action_for_key` (control.rs:99-106) dispatches digits
per scope — `SwitchWorkspace` in Spaces, `FocusAgent` in Agents — matching the
Phase 6 design bullet ("1..9 switches within the scope"), the DEFAULT_CONFIG
comment, the docs paragraph, and the per-scope test table. The log entry is
single-mode-era text that was never updated. In the same log, "One mode, not
three ... matches the ask" also needs a supersession note now that Phase 6 ships
three user-facing modes (the single-prefix mechanism argument survives; the
"matches the ask" framing does not).

**Correction**: rewrite the digit entry to the scoped behavior and mark the
one-mode entry as superseded by Phase 6 (internal `Mode::Control` retained).

## 4. MINOR — §2.3's position-math prose describes code that does not exist

**Plan text** (§2.3): "Position math uses `visible_workspace_order()`
(actions.rs:1294) with clamped, non-wrapping steps..."

**Code evidence**: the landed `workspace_root_move_target` (navigate.rs) never
calls `visible_workspace_order()`; it filters
`workspace_list_entries_expanded` to `indented: false` root entries — duplicating
the roots computation inside `workspace_move_block_params` (sidebar.rs:396-405).
The landed approach is sound and arguably safer than the plan's letter:
`visible_workspace_order()` includes indented children and respects collapse
state, both wrong for root-level stepping. But the plan text (the contract) names
a helper the implementation deliberately avoided, and the reasoning is recorded
nowhere.

**Correction**: amend §2.3 to the root-entries mechanism and why; optionally note
the dedup opportunity (one shared roots helper instead of two copies of the
filter).

## 5. MINOR (test adequacy) — Phase 1's promised event/persist-seam assertions never landed

**Plan text** (Phase 1, Test): "event/persist side effects observed through the
same seams the mouse tests use (mirror `api_tab_move_reorders_tabs_in_target_workspace`
... and `move_workspace_reorders_without_changing_logical_selection` ...)."

**Code evidence**: the landed reorder tests (navigate.rs:
`move_tab_actions_reorder_with_gap_insert_and_clamp_at_edges`,
`move_workspace_actions_*`) assert order, focus, and mode only. No `event_hub`
or snapshot assertions — contrast the sidebar drag test, which asserts
`WorkspaceMoved` events and snapshot persistence for the same mutation.

**Failure scenario**: rewiring the keyboard arms from the via_api path to direct
state mutation (dropping event emission and persistence) passes every landed test.

**Correction**: add an event assertion to one tab-move and one workspace-move
test (the seams already exist in the test App), or amend the Phase 1 test bullet
to record that this coverage was deliberately dropped and why.

## 6. MINOR (test adequacy) — Phase 6's "Render: three badges; help overlay filter matches the new groups" is only partially landed

**Code evidence**: `scoped_mode_bars_render_for_both_tab_bar_positions_and_narrow_widths`
(ui.rs) never changes `control_scope`, so only the TABS badge and the h/l nav
label are ever rendered under test; " SPACES ", " AGENTS ", and the k/j label are
asserted nowhere (a typo in either badge string compiles and passes).
keybind_help.rs received the new "tab / space / agent modes" group but its test
module got no additions — no test asserts the group exists or that the filter
matches its labels (Phase 6 test list promised both).

**Correction**: extend the render test across the three scopes (badge + per-axis
nav label) and add the Phase 6-style help row (group present, filter matches, live
labels), or reopen those two test bullets.

## 7. MINOR (test adequacy) — the §0 remote-overlay trap has no test for any of the 19 new fields

**Plan text** (§0): "New key fields that skip this overlay silently vanish in
remote attach." Phase 7's test list says "remote overlay carries the three new
fields (mirror the local_profile expectations)".

**Code evidence**: the wiring is complete (verified field-by-field), but no test
round-trips any control/mode/reorder field through
`local_profile` → `parse_client_keybindings`; the client_transport tests cover
prefix/new_tab/custom-commands only. There are no "local_profile expectations" for
Phase 7 to mirror. A future field omitted from the overlay (the exact Phase 7
copy-paste risk) vanishes silently, as §0 itself warns.

**Correction**: one test: user config setting e.g. `tab_mode = "ctrl+t"` and
`control_down = "d"` survives the overlay round-trip into the client keybinds.

## 8. MINOR — Phase 1's checkbox test count does not match the tree

**Plan text** (Phase 1, Verify): "[x] `just check` green (full gate incl.
windows-lint; 10 new tests: ...)".

**Code evidence**: six tests in the current tree trace to Phase 1 (five in
navigate.rs plus `move_bindings_parse_and_conflict_like_other_actions` in
keybinds.rs). If the Phase 6 rework consolidated or deleted the other four, the
plan — which presents itself as the complete history and was amended
retroactively for exactly this reason (Phase 6b note) — should say so; as written
the count is unverifiable.

**Correction**: reconcile the count or annotate the Phase 6 rework's test
consolidation in the Phase 1 verify line.

---

No blocker: the implementation is faithful to the reviewed design in every
load-bearing mechanism I could execute or read, the full gate is green right now,
and the two MAJORs are holes in the test contract (one vacuous, one absent) rather
than runtime defects.

Awaiting imp_agent_reply_1.md.
