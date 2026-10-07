# Herdr control mode implementation plan

Goal: a new sticky keyboard mode (working name: **control mode**, `Mode::Control`) that
gives zellij-style modal control over **tabs, agents, and spaces (workspaces)** from one
entry key, with its own configurable keymap, its own bottom mode bar in the UI, and new
reorder actions (move tab / move workspace) that are also bindable outside the mode.

Everything here was verified against the local clone at commit `10974c82`
(`feat(input): add per-pane right-click routing (#2504)`). File:line anchors are from
that commit; re-verify anchors after any `git pull`.

---

## 0. Verified stack and the traps already found

- **Local build**: `./build_and_install_local.sh` -> `~/.local/bin/herdr`. Needs brew
  `zig@0.15`. The script builds against a repo-local patched copy of zig's lib dir
  (`.zig-lib-0.15-patched/`, created on first run) because the macOS 26 SDK hides the
  `INFINITY` macro from zig 0.15's bundled libcxx. Never patch the brew keg itself.
  `-Dsimd=false` is NOT an escape hatch here: that archive fails Apple's linker with a
  `compiler_rt.o` alignment error. Root cause disappears when upstream moves to zig 0.16
  (herdrdev/herdr#285).
- **`herdr update` will clobber the local binary** with the stable release. Do not run it
  while on a source build.
- **Toolchain gaps on this machine**: `just`, `cargo-nextest`, and `bun` are not
  installed. `just test` needs all three (the justfile's `integration-assets-test`
  and `plugin-marketplace-test` recipes run `bun test`, justfile:65-71). `just check`
  additionally runs `windows-lint` (cross-target clippy of the vendored build script
  with `rustup target add x86_64-pc-windows-msvc`), which is untested on this host and
  in the same fragility class as the zig toolchain issues above. Phase 0 installs all
  three and runs the FULL gate once on the unmodified baseline so any narrower-gate
  decision is made up front, not mid-feature.
- **Repo guardrails (CLAUDE.md)**: state is pure data (`AppState` testable without
  PTYs), render never mutates, no `unwrap()` in production code, `tracing` for logs,
  lowercase conventional commits with `refs #<issue>` bodies. Planning notes normally
  live under `.local/prd/`; this PLAN.md stays untracked via `.git/info/exclude`.
- **External contributor status**: we are not maintainers and not in
  `.github/APPROVED_CONTRIBUTORS`. Unsolicited implementation PRs are auto-closed.
  Upstreaming means proposing in GitHub Discussions first. Until then this is a local
  patch carried on our clone.
- **This file's location**: the repo convention puts planning notes in `.local/prd/`;
  this file sits at the repo root deliberately, matching the owner's cross-project
  convention (covalent PLAN.md at root), and stays out of git via `.git/info/exclude`.
  Anchors in this file point at declaration lines (the `fn`/`struct`/`enum` line), not
  LSP symbol ranges that start at attributes or doc comments.
- **Config reference parity is enforced by CI-grade scripts**:
  `scripts/config_reference_check.py` walks the serde structs under `src/config/*.rs`
  from root `Config` and diffs the dotted key set against
  `docs/next/website/src/data/config-reference.json`. Every new `[keys]` field must land
  there or `just test` fails (real-tree check via
  `test_preview_reference_matches_real_config_model`). Translation parity for the
  `ja`/`zh-cn` doc trees is DIFFERENT: `scripts.test_docs_translation_parity` in
  `just test` is fixture-only; the real-tree parity check
  (`scripts/docs_translation_parity.py` against `docs/next`) runs only in
  `just release-docs-check`. Phase 4 runs that script directly so translation debt
  does not hide until release time.
- **The wire protocol is untouched by this feature.** Mode + keymap is TUI presentation
  state per the runtime/client boundary guardrail. Tab/workspace mutations reuse
  existing API methods (`tab.move`, workspace move); no `PROTOCOL_VERSION` bump.
- **Remote keybinding overlay trap**: `KeysConfig::local_profile()`
  (src/config/model.rs:649) builds the keybinding profile used by
  `herdr --remote --remote-keybindings local`. New key fields that skip this overlay
  silently vanish in remote attach. Every new field must be wired into
  `KeysConfigOverlay`, the `apply_field!`/`copy_user_field!` macros, and
  `user_fields` tracking (model.rs:645). [Round-3 audit: this trap now has a
  regression test - `local_profile_round_trip_carries_scoped_mode_and_reorder_fields`
  in client_transport.rs round-trips user-set and default fields through
  `local_keybindings_profile_toml` -> `parse_client_keybindings`; Phase 7's
  "mirror the local_profile expectations" now has a concrete test to extend.]
- **Mode-local plain keys have a reserved-key contract**: navigate mode pre-reserves
  exactly esc, enter, tab, backtab/shift+tab, left, right, and `1..9`
  (`reserve_navigate_runtime_keys`, src/config/keybinds.rs:699-719; wired at 452-454).
  Control mode ships the analogous contract with its own `BindingRegistry`, reserving
  what ITS handler hardwires: esc, enter, the prefix combo, `1..9`, and all four
  arrows (up/down included because control hardwires them for workspaces, unlike
  navigate where they are rebindable). Tab/backtab are not reserved because control
  mode does not hardwire them.
- **Testing a dev binary from inside a herdr session** needs
  `env -u HERDR_SOCKET_PATH -u HERDR_CLIENT_SOCKET_PATH cargo run -- <cmd>` so it talks
  to the debug server, not the installed one.

## 1. How the machinery works today (anchors)

### 1.1 Modes and key dispatch

- `Mode` enum: src/app/state.rs:817 (20 variants). `impl Mode` provides
  `mouse_motion_changes_view` (842) and `wants_ascii_input` (856, lists
  Prefix/Navigate/Navigator/Copy/Resize/ConfirmClose...). New modes must decide
  membership in both.
- Key routing: `App::handle_key` (src/app/input/mod.rs:78) matches `self.state.mode`;
  one arm per mode (93-122). Adding a mode = new arm + handler.
- Prefix mode handler: `handle_prefix_key` (src/app/input/navigate.rs:60). Order:
  prefix-key double-press pass-through -> esc -> `non_indexed_action_for_key` ->
  custom `[[keys.command]]` bindings -> indexed (`1..9`) bindings -> unknown key exits
  via `leave_command_mode`.
- Sticky mode template: resize mode, `handle_resize_key_via_api`
  (src/app/input/modal.rs:1127). Exits on esc/enter/its own toggle binding; hardcoded
  hjkl/arrows; acts through `runtime_pane_resize` ("via_api" pattern).
- Mode exit helpers: `leave_navigate_mode` (navigate.rs:1813), `leave_command_mode`
  (1839; falls back to `Mode::Navigate` when no workspace is focused),
  `finish_action_context` (1819).

### 1.2 Actions

- `NavigateAction` enum (navigate.rs:1334) is the single action currency for direct,
  prefix, and navigate dispatch. `execute_tui_navigate_action(action, context)`
  (navigate.rs:183) implements every arm; `ActionContext::{Direct,Prefix,Navigate}`
  (navigate.rs:47) controls post-action mode restoration.
- Binding -> action mapping is one declarative table in `non_indexed_action_for_key`
  (navigate.rs:1470-1528); indexed bindings (switch_tab/switch_workspace/focus_agent)
  in `indexed_navigation_action` (1405).
- Tab/workspace/agent verbs already implemented as arms: NewTab (289), FocusAgent (252),
  Previous/NextAgent (275/282, via `relative_agent_entry` +
  `focus_pane_internal_via_api`), Previous/NextWorkspace (263/269), etc.
- **Reordering exists but is mouse-only**: drag on the tab bar
  (`DragTarget::TabReorder`, state.rs:1133; drop -> `MouseAction::MoveTab`,
  input/mouse.rs:884 -> `move_tab_via_api(ws_idx, source_tab_idx, insert_idx)`,
  input/mod.rs:435). Same for workspaces (`MouseAction::MoveWorkspace` ->
  `move_workspace_via_api`, input/mod.rs:427). Server side is done:
  `handle_tab_move` (src/app/api/tabs.rs:181), `TabMoveParams { tab_id, insert_index }`
  (src/api/schema/tabs.rs:34), emits `tab.moved`. No keyboard path, no CLI subcommand,
  no context-menu item.

### 1.3 Keybinding configuration

- `Keybinds` struct: src/config/keybinds.rs:307 (~45 `ActionKeybinds` fields + 3 indexed
  vectors + `NavigateKeybinds` + custom commands). `ActionKeybinds` (167) carries
  parsed direct and prefix triggers; `IndexedKeybind` (260) handles `1..9` ranges;
  `NavigateKeybinds` (296) is the existing mode-local plain-key struct to imitate.
- Parsing/validation: `Config::validated_keybinds()` (keybinds.rs:434) builds two
  `BindingRegistry` instances (380; direct + prefix namespaces, first-wins conflict
  diagnostics) and a separate navigate registry with reserved runtime keys. Diagnostics
  surface in `herdr config check` and in-app via `config_diagnostic`.
- Config model: `KeysConfig` (src/config/model.rs:335). Doc comments on fields feed the
  config reference checker. `user_fields` tracks which fields the user actually set
  (645); `local_profile` (649) builds the remote-attach overlay.
- The commented reference config printed by `herdr --default-config` is one big string:
  `DEFAULT_CONFIG` (src/main.rs:109). It must be updated by hand for new keys.

### 1.4 UI

- Render entry: src/ui.rs render() -> mode overlay match (431-459). Mode bars replace
  the bottom row: `mode_bar_area` (422) is the tab bar row when
  `tab_bar_position = "bottom"`, else the terminal area's last line.
- Bar implementations: src/ui/menus.rs `render_prefix_overlay` (31),
  `render_copy_mode_overlay` (63), `render_navigate_overlay` (130),
  `render_resize_overlay` (259). Pattern: accent-bg " MODE " badge span + key spans in
  accent bold + dim label spans, drawn via `render_bottom_bar` (22). Key labels come
  from live keybinds (`prefix_rhs_label`, `keybind_label`), never hardcoded when a
  binding is configurable.
- Mouse interplay: `mode_bar_covers_tab_row` (src/app/input/mouse.rs:1287) lists the
  modes whose bar swallows tab-row clicks; a new bottom-bar mode must join that list
  (regression test exists: `bottom_mode_bar_consumes_hidden_tab_mouse_actions`,
  mouse.rs:3520).
- Keybind help overlay: groups built in `keybind_help_groups`
  (src/ui/keybind_help.rs:62); new mode gets its own group with live labels.

### 1.5 Tests conventions

- In-module `#[cfg(test)]`, run by `cargo nextest` via `just test`.
- Pure-state tests: `AppState::test_new()` (state.rs:1728),
  `execute_navigate_action` test helper (navigate.rs:1570),
  `action_for_key` test helper (1461).
- Identity/state invariants: `AppState::assert_invariants_for_test()` (state.rs:1928)
  with `test_with_adversarial_identity_state` (1919). The invariant checker already
  validates `DragTarget::TabReorder` indices (2163-2178).
- UI render tests assert on buffer rows (`buffer_row_text`, e.g. ui.rs:815-899 asserts
  the PREFIX bar lands on the right row for both tab bar positions).

## 2. Feature design

### 2.1 Mode semantics

- `Mode::Control`, entered by a bindable action `NavigateAction::EnterControlMode`
  (config field `control_mode`, an `ActionKeybinds` like `resize_mode`). Upstream-safe
  default: `"prefix+t"`. Personal config will set `"ctrl+t"` (direct trigger) to match
  zellij tab-mode muscle memory.
- Sticky like resize mode. Exits: esc, enter, or the `control_mode` binding again, with
  `leave_command_mode` semantics (Terminal if a workspace is focused, else Navigate).
  The prefix key ALSO exits, which is a deliberate divergence from the resize template
  (resize keeps a bare prefix press inert, modal.rs:1142-1148): pressing the prefix in
  control mode exits INTO prefix mode, so `ctrl+t ... ctrl+b c` chains naturally.
  Tested explicitly in Phase 2.
- Zellij-faithful stickiness rule: **navigation and reorder keys keep the mode; keys
  that create, rename, or close leave it** (rename/new hand off to their modals, which
  are separate modes anyway; close returns to Terminal).
- Mouse: clicks inside panes fall through as today for other sticky modes; the bar
  swallows tab-row clicks (`mode_bar_covers_tab_row` + `Mode::Control` in the match).
- `Mode::Control` joins `wants_ascii_input` (IME correctness) and stays out of
  `mouse_motion_changes_view`.

### 2.2 Default control keymap (all configurable, flat fields like `navigate_*`)

Tabs                         | Spaces (workspaces)             | Agents
---------------------------- | ------------------------------- | -------------------------
`n` new tab                  | `shift+n` new workspace         | `a` next agent
`r` rename tab               | `shift+r` rename workspace      | `shift+a` previous agent
`x` close tab                | `shift+x` close workspace       |
`h` / `left` previous tab    | `k` / `up` previous workspace   |
`l` / `right` next tab       | `j` / `down` next workspace     |
`i` move tab left            | `shift+k` move workspace up     |
`o` move tab right           | `shift+j` move workspace down   |
`1..9` switch tab (reserved) |                                 |

Reserved and non-configurable inside the mode: `esc`, `enter`, the prefix key, `1..9`,
and all four arrow keys (tab/backtab deliberately not reserved; not hardwired) — the
same set section 0 states and the Phase 2 registry enforces.
Config section: flat `control_*` keys in `[keys]` mirroring the `navigate_*` precedent
(`control_new_tab = "n"`, ..., `control_move_tab_left = "i"`, etc.). Arrows remain
hardwired fallbacks for prev/next like navigate mode's arrow contract.

### 2.3 New reorder actions (also usable without the mode)

Four new `NavigateAction` variants backed by the existing via_api mutations:

- `MoveTabLeft` / `MoveTabRight`: active workspace, focused tab, via `move_tab_via_api`.
  `Workspace::move_tab(source_idx, insert_idx)` (workspace.rs:637-660) takes a GAP
  index with a `source < insert` adjustment, so move-right-by-one is
  `move_tab(i, i+2)` and move-left is `move_tab(i, i-1)`; `move_tab(i, i+1)` computes
  `target == source` and silently no-ops. No wrap (drag does not wrap either); at the
  edges make no call (`handle_tab_move` rejects `insert_index > tabs.len()` with an
  API error, api/tabs.rs:188-194). Focused-tab tracking needs no new logic: `move_tab`
  re-derives `active_tab` by root-pane identity (workspace.rs:653-658); the Phase 1
  test characterizes that existing behavior.
- `MoveWorkspaceUp` / `MoveWorkspaceDown`: mirror the mouse DROP path's classification
  (mouse.rs:849-872), which is not a single API call: a workspace inside a worktree
  space moves as a BLOCK (`workspace_move_block_params` ->
  `move_workspace_block_via_api`; `AppState::move_workspace_block`, actions.rs:1398,
  collects even non-contiguous group members), while only standalone workspaces use
  `move_workspace_via_api` with an id-derived insert index. Position math steps over sidebar ROOT
  entries (`workspace_list_entries_expanded` filtered to `indented: false`, the
  same computation `workspace_move_block_params` uses) with clamped, non-wrapping
  steps - `visible_workspace_order()` was deliberately not used because it includes
  indented children and respects collapse state, both wrong for root-level
  stepping; do NOT reuse `relative_visible_workspace` (navigate.rs:714) either,
  which wraps via `rem_euclid`. (Round-3 note: the two root-filter copies in
  navigate.rs and sidebar.rs are a dedup opportunity, not a defect.) A collapsed group occupies one visible slot but several actual
  indices, so "up one visible position" must clear the entire neighboring group.

Also exposed as four normal top-level bindings (default unset, like
`previous_workspace`): `move_tab_left`, `move_tab_right`, `move_workspace_up`,
`move_workspace_down`. Personal config binds `alt+i` / `alt+o` for tabs (zellij).

## 3. Testing strategy (global)

- `just check` green is the phase gate everywhere (fmt + clippy -D warnings + nextest +
  maintenance scripts). Maintenance scripts cover config-reference parity (real tree),
  changelog shape, and vendored-patch hygiene, so that docs debt fails fast;
  translation parity is fixture-only there and gets its real-tree run in Phase 4
  (see section 0).
- Every state change gets a pure `AppState::test_new()` test first; no PTYs.
- Adversarial pass per phase that touches identity/order:
  `assert_invariants_for_test` after executing the new actions on
  `test_with_adversarial_identity_state`.
- Manual validation happens in a disposable named session against the dev server:
  `env -u HERDR_SOCKET_PATH -u HERDR_CLIENT_SOCKET_PATH cargo run -- --session plansmoke`.
- Keep a written manual matrix per phase in this file, checked off like the automated
  ones.

---

## 4. The phases

Each phase ends with: `just check` green, this file's checkboxes updated, and the
binary reinstalled via `./build_and_install_local.sh` when user-visible.

### Phase 0 - Toolchain and baseline

**Goal**: the project's own validation loop runs green locally before any edit.

**Implement**
1. `brew install just cargo-nextest bun` (bun: the justfile's integration-asset and
   plugin-marketplace test recipes run through it).
2. [x] Add `PLAN.md` to `.git/info/exclude` (done, alongside the build script,
   zig-lib copy, `.cargo/`, and `adv_convo1/`).
3. Run `just test`; capture runtime and any pre-existing failures (expected: none).
4. Run the FULL phase gate `just check` once on the unmodified baseline. If
   `windows-lint` (cross-target clippy + `rustup target add x86_64-pc-windows-msvc`)
   fails on this host, decide the narrower gate NOW and record it here with the exact
   reason (CLAUDE.md requires naming why a narrower check is enough); Phases 1-4 then
   cite that decision instead of discovering it mid-feature.

**Verify**
- [x] `just test` green on unmodified `10974c82` (3121/3121 passed).
- [x] `just check` green on unmodified `10974c82`, windows-lint included — no narrower
      gate needed. One flake observed and characterized:
      `api::server::pane_graphics_stream::tests::inactive_owner_cancels_idle_stream_and_dispatches_close`
      fails on Timeout under parallel load, passes 3/3 in isolation
      (`just test-one inactive_owner_cancels_idle_stream`); pre-existing, not ours.
- [x] `git status` clean apart from excluded local files.

### Phase 1 - Reorder actions (keyboard-facing action layer)

**Goal**: `move_tab_left/right`, `move_workspace_up/down` exist as `NavigateAction`s
and as top-level bindings, fully tested, before any new mode exists.

**Implement**
1. Add the four `NavigateAction` variants (navigate.rs:1334 enum) and their arms in
   `execute_tui_navigate_action`, with the exact semantics from section 2.3: tab moves
   use the gap-index arithmetic (`i+2` right, `i-1` left, no call at the edges);
   workspace moves classify worktree-space members into the block path
   (`workspace_move_block_params` -> `move_workspace_block_via_api`) and standalone
   workspaces into `move_workspace_via_api`, with clamped non-wrapping visible-order
   math. Reordering does not touch focus, so add all four to
   `copy_mode_survives_prefix_action` (navigate.rs:1382).
2. Add four `ActionKeybinds` fields to `Keybinds` (keybinds.rs:307), `KeysConfig`
   (model.rs:335 with doc comments), `validated_keybinds` table, the
   `non_indexed_action_for_key` table (navigate.rs:1476), `KeysConfigOverlay` +
   `apply_field!` + `local_profile`, defaults unset (`ActionKeybinds::default()`).
3. Wire `keys.indexed`-style docs later (Phase 4); code-level docs comments now.

**Test**
- Unit: action arms on `AppState::test_new()` with 3 tabs / 3 workspaces: middle moves
  both directions, edges no-op with no API call, focused tab follows its tab (pure
  characterization: `move_tab` already re-derives `active_tab` by root-pane identity),
  event/persist side effects observed through the same seams the mouse tests use
  (mirror `api_tab_move_reorders_tabs_in_target_workspace`, src/app/api/tabs.rs:384,
  and `move_workspace_reorders_without_changing_logical_selection`,
  src/app/actions.rs:4551). [Round-3 audit: the event-seam assertions had not
  landed; TabMoved/WorkspaceMoved event assertions added to one tab-move and one
  workspace-move test via `app.event_hub.events_after(0)`.]
- Worktree grouping: move a parent-with-children up/down past a standalone workspace
  and assert the group stays adjacent and ordered (block path taken); mirror
  `move_workspace_block_collects_non_contiguous_members` (actions.rs:4586) for the
  non-contiguous case.
- Binding: `action_for_key` resolves `move_tab_left = "alt+i"` (direct) and
  `"prefix+i"` (prefix) forms; conflict diagnostic fires when it collides with an
  existing direct binding.
- Adversarial: run both moves against `test_with_adversarial_identity_state` then
  `assert_invariants_for_test`.

**Verify**
- [x] `just check` green (full gate incl. windows-lint). Phase 1 added 6 new tests
      (5 in navigate.rs: gap-index clamps, block-move adjacency, standalone
      reorder, adversarial invariants, binding dispatch; 1 in keybinds.rs:
      conflict diagnostics) - the "10" previously recorded here was the nextest
      pattern-filter run count, which included pre-existing matches. [Corrected in
      the round-3 audit.]
- [ ] Manual: in `plansmoke` session with 3 tabs, `alt+i`/`alt+o` (temp user config)
      reorder the focused tab; sidebar and tab bar agree; order survives server restart
      (session persistence). [needs a human at the keyboard; queued for Phase 5]
- [ ] Mouse drag reorder still works (no regression in `mouse.rs` tests or by hand).

### Phase 2 - Mode::Control state and input

**Goal**: the mode exists, enters, dispatches its keymap, exits; still no UI bar.

**Implement**
1. `Mode::Control` variant (state.rs:817); membership: `wants_ascii_input` yes,
   `mouse_motion_changes_view` no.
2. `ControlKeybinds` struct in keybinds.rs modeled on `NavigateKeybinds` (296): fields
   per section 2.2, each `ActionKeybinds` (plain-key single bindings). Parse from flat
   `control_*` fields in `KeysConfig` with doc comments; validate through a dedicated
   `BindingRegistry` that pre-reserves esc, enter, the prefix combo, `1..9`, and all
   four arrows (the full hardwired set, per section 0) and emits diagnostics on
   intra-mode conflicts; wire `KeysConfigOverlay`/`local_profile`/`user_fields`.
3. `NavigateAction::EnterControlMode` + `control_mode` binding field (default
   `"prefix+t"`), arm sets `self.state.mode = Mode::Control` (mirror
   EnterResizeMode, navigate.rs:385).
4. `handle_control_key` in a new `src/app/input/control.rs` (match the module split
   convention): exit checks first (esc/enter/control_mode binding/prefix key), then
   the configured keys -> existing `NavigateAction`s (SwitchTab via hardwired `1..9`,
   Previous/NextTab, the four new move actions, Previous/NextWorkspace,
   MoveWorkspaceUp/Down, NewTab, RenameTab, CloseTab, NewWorkspace, RenameWorkspace,
   CloseWorkspace, Previous/NextAgent), then arrow fallbacks. Dispatch through
   `execute_tui_navigate_action` with a new `ActionContext::Control`.
5. Stickiness CANNOT hang off `finish_action_context`'s mode-unchanged check: the nav
   arms mutate the mode themselves (`Previous/NextTab` at navigate.rs:311-322,
   `Previous/NextWorkspace`, `Previous/NextAgent`, `SwitchTab`, `FocusAgent` all call
   `leave_navigate_mode`, which lands in Terminal), so "unchanged" never holds and
   cannot be told apart from a modal transition. Instead: an explicit
   `control_sticky_action(action) -> bool` predicate table (same idiom as
   `copy_mode_survives_prefix_action`, navigate.rs:1382) listing the
   navigation/reorder/agent actions; after
   `execute_tui_navigate_action(action, ActionContext::Control)`, if the predicate
   holds and `state.mode == Mode::Terminal`, set `state.mode = Mode::Control` back.
   Modal transitions (RenameTab, ConfirmClose) are untouched because they never land
   in Terminal; close/new stay correctly non-sticky by omission from the table; no-op
   paths (e.g. `relative_tab` -> None) leave the mode alone and need no handling.
6. Register the `Mode::Control` arm in `handle_key` (input/mod.rs:93) and in the
   catch-all mode matches that must not panic (`app/mod.rs:1805` region,
   input/mod.rs modal paste target check).

**Test**
- Unit (pure state, `AppState::test_new()`): enter via binding; every default key maps
  to its action; sticky actions keep `Mode::Control`; `n`/`r`/`x` leave to the correct
  mode (RenameTab modal, ConfirmClose flow honoring `confirm_close`); esc/enter exit
  to Terminal-with-focus and Navigate-without-focus; the prefix key exits INTO
  `Mode::Prefix` (the documented divergence from the resize template); unknown keys
  are inert (do NOT exit, matching resize mode's tolerance).
- Enum-coverage upkeep: add `Mode::Control` to the allowlist half of
  `mode_wants_ascii_input_classification` (app/mod.rs:2109) — it compiles without the
  edit and silently loses full-enum coverage, so the plan names it explicitly.
- Config: `control_*` overrides parse; reserved-key use produces the exact diagnostic
  string; `herdr config check` output asserted like existing keybinds tests.
- Adversarial invariants after a scripted key sequence (enter mode, move tab, close
  tab, move workspace, exit).

**Verify**
- [x] `just check` green (full gate). 9 new tests: entry desktop/mobile, the full
      default keymap table, stickiness, modal/close exits, prefix chaining, unknown-key
      inertness, empty-state exit, adversarial walk, reserved-key + prefix-syntax
      diagnostics, defaults parsing.
- [ ] Manual in `plansmoke`: `prefix+t` then the full section 2.2 keymap walked
      end to end; mode exits correctly from every path; IME/ascii switching unaffected.
      [needs a human at the keyboard; queued for Phase 5]

### Phase 3 - UI: mode bar, mouse guards, keybind help

**Goal**: control mode is visible and self-documenting, matching existing bars.

**Implement**
1. `render_control_overlay` in src/ui/menus.rs following `render_navigate_overlay`:
   " CONTROL " badge (accent bg, `panel_contrast_fg`), grouped hints with live labels
   from `ControlKeybinds` (`keybind_label` helpers): tabs cluster, spaces cluster,
   agents cluster, exit hint. Narrow widths clip on the right like every existing bar
   (a single `Line` drawn into a 1-row area; no bar has cluster-dropping logic and
   this one does not introduce any) — order the spans most-important-first so clipping
   degrades sanely.
2. Register in the ui.rs mode match (431) with `mode_bar_area`. Mobile: the
   `EnterControlMode` arm checks `view.layout == Mobile` and sets `Mode::Navigate`
   instead — Navigate IS the mobile-panel mode, exactly what the `WorkspacePicker`
   arm does (navigate.rs:259-262); rendering the mobile panel while
   `handle_control_key` owned input would break the panel's keys. The other path
   (enter on desktop, then narrow below `mobile_width_threshold` while in Control) is
   accepted as-is: layout flips, the desktop bar keeps drawing — identical to resize
   mode's behavior today; one comment in the arm records this.
3. Add `Mode::Control` to `mode_bar_covers_tab_row` (mouse.rs:1287).
4. New "Control mode" group in `keybind_help_groups` (keybind_help.rs:62) with live
   labels, plus the `control_mode` entry itself in the existing session group.

**Test**
- Render: buffer-row assertions for both `tab_bar_position` values (mirror ui.rs:815
  test) proving the badge and a known label land on the bar row; narrow-width
  render does not panic and keeps the badge. [Round-3 audit: only the TABS badge
  was covered; the test now walks all three scopes asserting each badge, the k/j
  axis label, and the absence of h/l on the vertical bars.]
- Mouse: extend `bottom_mode_bar_consumes_hidden_tab_mouse_actions` (mouse.rs:3520)
  to `Mode::Control`.
- Help overlay: group appears, filter matches its labels (mirror keybind_help tests).

**Verify**
- [x] `just check` green (full gate). Render tests cover both tab bar positions and
      narrow widths; the mouse-guard regression test now walks Control mode too; the
      help overlay gained a "control mode" group plus entries for `control_mode` and
      the four reorder bindings.
- [ ] Manual: bar renders with Catppuccin accent, both tab bar positions, resize the
      terminal narrow; tab-row clicks while in mode do not leak to tabs; `prefix+?`
      shows the new group. [needs a human at the keyboard; queued for Phase 5]

### Phase 4 - Config surface, reference docs, changelog

**Goal**: every config key documented everywhere the maintenance tests look, plus the
human-facing reference config.

**Implement**
1. `DEFAULT_CONFIG` template (src/main.rs:109): `control_mode` plus the commented
   `control_*` block in `[keys]`, matching the file's comment voice.
2. `docs/next/website/src/data/config-reference.json`: entries for every new dotted
   key (`keys.control_mode`, `keys.control_new_tab`, ...), wording consistent with
   neighbors. Run `python3 scripts/config_reference_check.py` directly first.
3. Keybindings section of the configuration docs page in
   `docs/next/website/src/content/docs/` (+ whatever
   `scripts/test_docs_translation_parity` requires for `ja`/`zh-cn`; inspect the
   script before editing to learn whether parity is structural or full-content).
4. `docs/next/CHANGELOG.md` entry (staged changelog, not root): feature line for
   control mode + keyboard tab/workspace reordering.

**Test**
- `just test` maintenance suite green (covers config reference against the real tree
  and changelog shape).
- Translation parity is NOT covered by `just test` (fixture-only there): run
  `python3 scripts/docs_translation_parity.py` directly against `docs/next` the way
  `just release-docs-check` does, and fix or explicitly record any ja/zh-cn gap this
  feature introduces.

**Verify**
- [x] `just check` green (final full-gate run pending at the time of writing; all
      maintenance scripts pass standalone: config reference, translation parity
      against docs/next, changelog shape).
- [x] Default template sanity: `cargo run -- --default-config` output parses clean
      via `HERDR_CONFIG_PATH=<tmp> herdr config check`; all 17 control keys present.
- [x] Docs edits stay inside existing headings (parity-safe); ja/zh-cn got the
      translated control-mode paragraph; changelog staged in docs/next/CHANGELOG.md.

### Phase 5 - Rollout, personal keymap, upstream path

**Goal**: running daily on the local build with the zellij-faithful personal keymap;
upstream contribution path decided explicitly.

**Implement**
1. Rebuild + reinstall (`./build_and_install_local.sh`), `herdr server stop`, relaunch,
   confirm session restore.
2. Personal `~/.config/herdr/config.toml`: `control_mode = "ctrl+t"`,
   `move_tab_left = "alt+i"`, `move_tab_right = "alt+o"`; drop the now-redundant
   tab-verb prefix remaps if control mode covers them better (decide by feel after a
   day; keep `prefix+n`/`prefix+r`/`prefix+h`/`prefix+l` until then).
3. Memory note update (assistant memory, not repo): final keymap and the fact the
   local build carries this patch series.
4. Upstream: open a GitHub Discussion describing the feature with the design from
   section 2 (external contributor guardrail forbids an unsolicited PR). If maintainers
   invite it, rebase the series on fresh `master` in a dedicated worktree per repo
   convention (`../herdr-worktrees/control-mode`).

**Verify**
- [x] `ctrl+t` conflict check: fzf.fish is NOT installed (fisher has only fisher +
      nvm.fish), so the file-widget conflict is moot; `ctrl+t` committed as the
      personal trigger. Fish's builtin transpose-chars on ctrl+t is sacrificed
      knowingly.
- [ ] `ctrl+t` from a fish pane enters control mode on this terminal (watch upstream
      issue #2514: alt/modifier events in fish panes on macOS 26 reportedly flaky in
      WezTerm; if `alt+i/o` do not fire, fall back to control-mode `i`/`o` only and
      note it here). [needs a human at the keyboard]
- [ ] One full day of daily driving without reaching for the mouse for tab/space/agent
      management. [needs a human at the keyboard]
- [ ] Rebase check: `git pull --rebase` on top of upstream master replays the series
      clean or conflicts are resolved and this file's anchors re-verified.
      [when upstream master next moves]

**Phase 5 execution log (2026-08-09)**
- [x] Rebuilt and installed via `./build_and_install_local.sh`; old server stopped,
      new server running (protocol 20), `herdr config check` ok.
- [x] Personal config: `control_mode = "ctrl+t"`, `move_tab_left = "alt+i"`,
      `move_tab_right = "alt+o"`; prefix tab verbs kept until a day of feel-testing.
- [ ] Upstream GitHub Discussion: NOT opened — outward-facing action requiring the
      owner's explicit go-ahead under the external-contributor guardrail.

---

### Phase 6 - Scoped modes rework: TABS / SPACES / AGENTS

**Goal**: replace the single user-facing "control mode" with three named modes, per
the owner's actual ask, without discarding the reviewed machinery.

**Design (supersedes the single-mode surface of section 2)**
- Internally one sticky mode remains (`Mode::Control`) with a new
  `AppState.control_scope: ControlScope { Tabs, Spaces, Agents }`; every exhaustive
  match, the mouse guard, ascii-input membership, and the remote overlay stay valid.
- User-facing: three modes with three entry bindings and three bar badges
  (" TABS ", " SPACES ", " AGENTS "). Upstream defaults: `tab_mode = "prefix+t"`,
  `space_mode = "prefix+shift+s"`, `agent_mode = "prefix+a"`. Personal:
  `tab_mode = "ctrl+t"` (zellij tab mode), `space_mode = "ctrl+o"` (zellij session
  mode), `agent_mode = "prefix+a"` (no safe free ctrl key; direct chord optional).
- One shared verb keymap, zellij-style same-letter-per-mode:
  `control_new = "n"`, `control_rename = "r"`, `control_close = "x"`,
  `control_move_back = "i"`, `control_move_forward = "o"`; `1..9` switches within
  the scope; arrows stay global (left/right tabs, up/down spaces) in every scope;
  scope switching inside the mode via `control_scope_tabs = "t"`,
  `control_scope_spaces = "s"`, `control_scope_agents = "a"`. Navigation is
  AXIS-SPLIT per owner feedback (2026-08-09): `control_previous = "h"` /
  `control_next = "l"` walk only the horizontal tab row; `control_up = "k"` /
  `control_down = "j"` walk the vertical space and agent lists; the off-axis pair
  is inert in each scope, and each mode's bar shows only its own axis. The 17 noun-specific `control_*` fields are REMOVED
  (never released, so no compatibility surface). No hardwired j/k aliases: they would
  silently shadow configurable letters, the exact conflict class the registry rejects.
- Scope verb mapping: Tabs -> tab actions incl. MoveTabLeft/Right and SwitchTab;
  Spaces -> workspace actions incl. block-aware MoveWorkspaceUp/Down and
  SwitchWorkspace; Agents -> Previous/NextAgent + FocusAgent 1..9; new/rename/close/
  move are inert in Agents scope (agents are not creatable/closable objects here).
- Exits and stickiness unchanged: esc/enter leave, prefix chains into prefix mode,
  unknown keys inert; scope switches keep the mode by early return in the handler,
  before dispatch - they are not (and need not be) in the sticky predicate, since
  they are not NavigateActions at all. Entry
  bindings toggle off from inside the mode WITH scope-switch precedence: the scope
  letters are checked first, so with defaults the bare `t`/`a` prefix-rhs letters
  switch scope rather than exit and only `shift+s` toggles off, while direct-form
  entry chords (the personal ctrl+t/o/g) always toggle off. [Precedence pinned by
  test in the round-3 audit.]

**Implement**
1. `ControlScope` + `control_scope` field (state.rs), default Tabs, set by the three
   entry arms (`EnterTabMode`/`EnterSpaceMode`/`EnterAgentMode` replace
   `EnterControlMode`; mobile still opens the panel).
2. Config surface swap in model.rs/keybinds.rs: 13 new fields in, 17 old fields out;
   `ControlKeybinds` becomes verbs + scope switches; same control registry and
   reserved set.
3. `handle_control_key`: scope-switch check, then scope-parameterized verb dispatch.
4. Bars per scope with live labels; help overlay regrouped as "tab / space / agent
   modes"; render + mouse tests updated to the TABS badge.
5. Docs: config-reference entries swapped, DEFAULT_CONFIG block rewritten,
   configuration.mdx paragraph (en/ja/zh-cn) rewritten, changelog entry reworded.

**Test**
- Rewritten control.rs suite: per-scope verb tables, scope switching stays in mode,
  agent-scope inert verbs, entry bindings set the right scope, mobile entry, exits,
  adversarial walk across all three scopes.
- Keybinds: new defaults parse, verb conflict diagnostics, entry bindings resolve.
- Render: three badges; help overlay filter matches the new groups.

**Verify**
- [x] `just check` green (full gate; 85 affected tests incl. per-scope verb tables,
      scope switching, agent-scope inertness, entry->scope mapping, adversarial walk
      across all three scopes).
- [x] Reference/parity/changelog scripts green standalone; default template parses.
- [x] Personal config updated (`tab_mode = "ctrl+t"`, `space_mode = "ctrl+o"`,
      `agent_mode = "prefix+a"` - later retuned to `ctrl+g` in Phase 6b),
      `herdr config check` ok, server restarted on the new binary.
- [ ] Manual keyboard walk of all three modes. [needs a human at the keyboard]

### Phase 6b - Axis-split navigation and personal keymap tuning [IMPLEMENTED, recorded retroactively]

Retroactive note: this work landed after Phase 6's gate as two follow-up passes
driven by owner feedback, without a plan entry at the time. Recorded here so the
plan remains the complete history and reviewers hold it to the same standard.

**Axis-split navigation** (design also reflected in the Phase 6 design bullet)
- New shared fields `control_up = "k"` / `control_down = "j"` through all five
  config layers (KeysConfig struct, KeysConfigOverlay, `apply_field!`, Default,
  `local_profile`), reference JSON entries, DEFAULT_CONFIG lines, doc comments.
- Dispatch split by orientation in `control_action_for_key`: `control_previous`/
  `control_next` (h/l) act only in the horizontal Tabs scope; `control_up`/
  `control_down` (k/j) act only in the vertical Spaces and Agents scopes; the
  off-axis pair is inert per scope. Arrows keep the global contract.
- Bars show only their own axis pair (per-scope nav label in
  `render_control_overlay`); help overlay split into "previous / next tab (tabs)"
  and "up / down (spaces, agents)" entries; docs updated in en/ja/zh-cn; reference
  descriptions of h/l re-scoped to tabs.
- Tests: per-scope verb tables gained the k/j rows and inert off-axis assertions in
  all three scopes; the spaces sticky test moved to `j`. [Round-3 audit: the `j`
  edit had silently missed (rustfmt-wrapped bytes) leaving the assertion vacuous on
  an inert `l`; fixed with `j` plus a `k` twin, and an entry-binding toggle-off
  test with scope-switch precedence was added alongside.]

**Personal keymap decisions** (user config only; no repo changes)
- `agent_mode = "ctrl+g"` after auditing ~/.config/skhd/skhdrc and the omniwm
  bindings: every chord there includes `cmd` (the only ctrl appearances are
  cmd+ctrl combos), so bare ctrl+letter reaches herdr untouched; shell-critical
  ctrl keys were ruled out (a/e begin/end-line, r history search, f fish
  autosuggest accept, w/u/k kill keys, p/n history, c/d/z/l untouchable); ctrl+g
  chosen because zellij's lock mode had already claimed it in panes and fish
  barely uses it.
- `tab_mode = "ctrl+t"` (zellij tab-mode key), `space_mode = "ctrl+o"` (zellij
  session-mode key).
- `toggle_sidebar = ["prefix+b", "ctrl+s"]`: array binding keeps the default;
  direct ctrl+s is intercepted by herdr before any pane sees it, so the XOFF
  flow-control freeze cannot occur inside herdr panes, and zellij's scroll mode
  had already claimed ctrl+s anyway.

**Verify**
- [x] `just check` green after the axis split (full gate); binary rebuilt,
      installed, server restarted; `herdr config check` ok and live reloads
      applied for both personal keymap passes.
- [ ] Manual axis walk: k/j navigates in SPACES and AGENTS with h/l inert there;
      h/l navigates in TABS with k/j inert; ctrl+g enters AGENTS; ctrl+s toggles
      the sidebar. [needs a human at the keyboard]

### Phase 7 - PANES mode (fourth scope) [IMPLEMENTED]

**Goal**: a fourth sticky mode, PANES, completing the noun set with the same grammar:
directional focus on `h/j/k/l`, `n` split, `x` close, `r` rename, `i/o` swap, `z`
zoom, `p` joining `t/s/a` as the in-mode scope hop. No new machinery: one more
`ControlScope` variant riding the existing mode.

**Design (verified against the tree as of the Phase 6 rework)**

- `ControlScope::Panes` variant (state.rs enum next to Tabs/Spaces/Agents); entry
  action `EnterPaneMode` beside the other three (navigate.rs entry arm + twin), config
  `pane_mode`. Upstream default `"prefix+f"` (free: p is previous_tab, shift+p is
  rename_pane; f has no upstream binding). Personal binding `ctrl+p` - zellij's own
  pane-mode key, already sacrificed in the user's panes, skhd/omniwm are cmd-only.
- Panes are the first 2D scope, and the axis-split fields cover it exactly:
  `control_previous`/`control_next` (h/l) -> FocusPaneLeft/Right,
  `control_up`/`control_down` (k/j) -> FocusPaneUp/Down. No field changes needed;
  only new match arms in `control_action_for_key` (control.rs).
- Verbs in Panes scope:
  - `control_new` (n) -> auto-directional split like zellij's NewPane: split right
    when the focused pane's rendered rect is wide, split down when tall. Threshold
    from `view.pane_infos` rect with a cell-aspect factor; exact constant decided at
    impl time behind a characterization test (wide pane -> SplitVertical arm, tall
    pane -> SplitHorizontal arm; both arms exist, navigate.rs
    `split_focused_pane_via_api`). When no focused-pane rect is available (before
    the first layout pass, or pure-state tests without `compute_view`), default to
    SplitVertical - split right, zellij's fixed default; a zoomed pane reports the
    full terminal rect, so `n` while zoomed splits right, accepted and documented.
    Split exits the mode (create-leaves rule, matching zellij pane-mode n).
  - `control_close` (x) -> ClosePane (existing confirmation flow
    `close_focused_pane_via_api_requires_confirmation`; non-sticky).
  - `control_rename` (r) -> RenamePane (modal; non-sticky).
  - `control_move_back`/`control_move_forward` (i/o) -> SwapPaneLeft/SwapPaneRight.
  - NEW shared field `control_zoom = "z"` -> Zoom in Panes scope, inert in the other
    three scopes for now (z is free in the verb space; documented as panes-only).
- Sticky set additions: only SwapPane* and Zoom, whose arms call
  `leave_navigate_mode`. FocusPane* needs no sticky-set entry:
  `focus_pane_direction_in_context` (navigate.rs:593) never mutates the mode
  outside Navigate context, so Control keeps the mode by construction (adding the
  focus actions to `control_sticky_action` anyway is harmless self-documentation).
  Splits, close, rename stay non-sticky by omission.
- `1..9` in Panes scope: INERT initially. Panes carry no visible ordinals, so blind
  indexed focus is a misfire generator; pane index badges rendered during Panes scope
  would fix that properly and are explicitly out of scope here (decisions log).
- Arrows stay global (left/right tabs, up/down spaces) even in Panes scope, keeping
  the one-contract-everywhere rule; hjkl is the pane grammar. Decisions log entry.
- Bar: " PANES " badge; clusters: hjkl focus, n split, i/o swap, z zoom, r rename,
  x close, t/s/a/p scopes, esc done. All four bars' scope cluster grows to
  `t/s/a/p` labels from the four scope fields.
- Reserved keys unchanged (esc/enter/prefix/1..9/arrows); `control_scope_panes = "p"`
  is an ordinary configurable field like the other three switches.

**Implement**
1. state.rs: `ControlScope::Panes`; no new AppState fields.
2. navigate.rs: `EnterPaneMode` variant, entry-table row (`&kb.pane_mode`), entry
   arm + twin arm scope mapping, `control_scope_for_entry` arm.
3. keybinds.rs: `pane_mode` + `control_zoom` + `control_scope_panes` fields
   (Keybinds + ControlKeybinds + init + apply wiring; same registries).
4. model.rs: the three new config fields through struct/overlay/apply_field/
   Default/local_profile, doc comments stating scope applicability.
5. control.rs: Panes arms in `control_action_for_key` (2D axis mapping, auto-split
   helper reading the focused pane rect with the SplitVertical fallback, zoom,
   swaps); scope-switch table row; sticky-set additions; `control_zoom`
   inert-elsewhere match arms; extend `control_entry_binding_matches`
   (control.rs:66) with `&state.keybinds.pane_mode` and update its "three entry
   bindings" doc comment to four - it is a plain array, so nothing else will catch
   the omission.
6. menus.rs: PANES bar; scope cluster label extended to four; gate the `1-9 go`
   cluster on `scope != ControlScope::Panes` (it is pushed unconditionally at
   menus.rs:305 and would otherwise advertise deliberately inert keys).
   keybind_help.rs: entries for pane_mode, the panes grammar line, and zoom, plus
   the literal group title "tab / space / agent modes" (keybind_help.rs:191) and
   the "exit tab/space/agent mode" entry reworded to include panes.
7. Docs: config-reference entries (pane_mode, control_zoom, control_scope_panes,
   plus re-scoped descriptions where "space/agent" wording changes), DEFAULT_CONFIG
   template block, configuration.mdx paragraph extension in en/ja/zh-cn, changelog
   line amendment.

**Test**
- Per-scope verb table gains a Panes row: hjkl -> the four focus actions, n -> the
  split action chosen by rect shape (one wide case, one tall case), x/r/i/o/z, digits
  inert, off-scope verbs for the other scopes unchanged (h/l still inert in Spaces).
- `control_zoom` inert in Tabs/Spaces/Agents; zoom toggles and stays sticky in Panes
  (zoomed pane focus-moves already covered by existing
  `navigate_pane_changes_focus_while_zoomed`; the new test asserts mode retention).
- Entry test extended to the fourth (entry -> Mode::Control + ControlScope::Panes;
  mobile -> Navigate), AND the exit suite gains the toggle-off row: the pane_mode
  binding pressed inside Panes scope leaves the mode (the entry-binding array is
  the one surface no compiler error covers).
- Auto-split characterization: wide rect -> SplitVertical, tall rect ->
  SplitHorizontal, absent rect -> SplitVertical fallback.
- Help overlay: group renamed to cover panes, filter matches "pane", pane_mode and
  zoom entries present with live labels (the Phase 6-style row this phase edits).
- Scope-hop test extended: p from any scope; t/s/a/p round-trip.
- Config: pane_mode default parses, control_scope_panes conflicts diagnose, remote
  overlay carries the three new fields (mirror the local_profile expectations).
- Render: PANES badge both tab-bar positions, asserting the bar does NOT contain
  `1-9` (inert keys must not be advertised); adversarial walk extended to the
  fourth scope.

**Verify**
- [x] `just check` green (full gate) with the extended suites: fourth-scope entry,
      per-scope verb table incl. zoom-inert rows, wide/tall/absent auto-split
      characterization, pane sticky walk (focus/swap/zoom stay, split leaves),
      pane_mode toggle-off row, t/s/a/p hop, adversarial walk across four scopes,
      PANES bar with no 1-9 advertised, help overlay with pane entries, overlay
      round-trip carrying pane_mode + control_zoom.
- [x] Reference/parity/changelog scripts green standalone; default template carries
      all pane keys.
- [x] Personal config gains `pane_mode = "ctrl+p"` (zellij pane-mode key, completing
      the four repurposed zellij chords); `herdr config check` ok; server restarted
      on the new binary.
- [ ] Manual: ctrl+p, walk focus/split/swap/zoom/close in a real split layout; verify
      auto-split direction feels right in both wide and tall panes.
      [needs a human at the keyboard]

### Phase 8 - build_and_install.sh (source build + install for the fork)

**Goal**: one script at the repo root that takes a fresh macOS or Linux glibc box
to `~/.local/bin/herdr` built from this checkout: Rust via rustup if missing, the
right zig 0.15 for the vendored libghostty-vt, the binary installed without ever
leaving a broken one over a working install, and `~/.local/bin` put on PATH for
the shell the user actually runs. Supersedes the git-excluded
`build_and_install_local.sh`. Intent record: `research/intent.md`.

**Verified facts (2026-08-22/23, this host: macOS 26.5.2, Xcode-beta 27.0 SDK +
CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
- `build.rs` runs `$ZIG build ...` (falls back to `zig` on PATH); CI pins zig
  0.15.2 (mlugg/setup-zig on Linux, `HOMEBREW_NO_AUTO_UPDATE=1 brew install
  zig@0.15` on macOS). `rust-toolchain.toml` pins 1.96.1 and rustup honors it on
  first `cargo` call - but ONLY a rustup-managed cargo does: a distro cargo
  (debian bookworm ships cargo 0.66/rustc 1.63, which cannot even parse this
  `Cargo.lock` v4) ignores the pin, so the script gates on `rustup`, not `cargo`,
  and prepends `~/.cargo/bin`. `cmake`/`ninja` from CI are not herdr dependencies
  (absent from Cargo.lock).
- **The official zig 0.15.2 macOS tarball cannot link on current macOS.** Since
  Xcode 26.4 Apple's `libSystem.tbd` lists only `arm64e-macos` (no
  `arm64-macos`; true of both the CLT 26.5 and the Xcode-beta 27.0 SDK). zig
  0.15.2's MachO `TargetMatcher` never tries `arm64e`, so `-lSystem` resolves
  nothing and every libSystem symbol is undefined - even for zig's own build
  runner. Homebrew's `zig@0.15` backports the upstream fix (formula patch on
  `src/link/MachO/Dylib.zig`), which is why CI's step is named "Install patched
  Zig on macOS". Proof: fresh-cache `zig build-exe hello.zig` exits 1 with the
  tarball, 0 with brew's zig; identical `zig ld` lines. A warm `~/.cache/zig`
  masks this completely (the build runner is a cache hit), so any macOS test
  must use fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`. The brew formula
  is `deprecate! 2027-04-15` / `disable! 2028-04-15`: after that date the macOS
  branch stops working unless upstream has moved to zig 0.16 (herdrdev/herdr#285).
- The macOS 26 SDK INFINITY/libcxx problem from section 0 still applies on top
  (confirmed: unpatched brew zig fails `sub-compilation of libcxx ...
  clamp_to_integral.h: use of undeclared identifier 'INFINITY'`): a private
  patched copy of the lib dir (209 MB / 18,101 files, under
  `~/.local/share/herdr`, never the keg, keyed by `zig version`) plus a one-line
  wrapper exported as `ZIG`. Copies for superseded zig point releases are NOT
  pruned - accepted, it is a cache; delete old `zig-lib-*-patched` dirs by hand.
- Linux: the official tarball is fine (`zig-<arch>-linux-0.15.2.tar.xz`, 200 for
  both arches; the pre-0.14 spelling 404s); the build additionally needs a C
  compiler/linker for the Rust crates (`linker cc not found` otherwise) and
  `xz` for the tarball. `need cc` runs on both platforms but only means
  something on Linux: macOS ships `/usr/bin/cc` as an xcode-select shim that
  exists before any developer tools are installed, so macOS CLT coverage rides
  on `need brew` (Homebrew's installer requires the CLT). A broken SDK state (as
  `xcrun --show-sdk-version` is on this host today) surfaces as a zig error
  mid-build; accepted.
- `install(1)` replaces atomically on macOS but GNU `install` unlinks first, so
  the script installs to `.herdr.new` and `mv`s; macOS and Linux both leave a
  running herdr process undisturbed (inode changes, confirmed both sides).
- `$SHELL` is the passwd login shell, not the interactive one: on this host it
  is `/bin/zsh` while the owner runs fish with a populated `fish_user_paths`
  and no `~/.zshrc`. But a `~/.config/fish` dir is created by a single `fish -c`
  and proves only that fish was ever run. So the script does not choose: when a
  fish config exists it adds to `fish_user_paths`, AND it still edits the
  `$SHELL` rc (unless `$SHELL` is fish). Over-adding is cheap (a duplicate PATH
  entry, a `~/.zshrc` the owner never opens - the known cosmetic cost on the
  owner's own Mac); a missing entry is the failure. bash login shells read only the first of
  `.bash_profile`/`.bash_login`/`.profile`, so on macOS an existing `.profile`
  is appended to rather than shadowed by a new `.bash_profile`.
- `fish_add_path -U` exits 1 when nothing was added (fish 4.8.1); rustup's own
  profile edits are skipped (`--no-modify-path`).
- After this script installs a fork build, herdr's in-app updater
  (`src/update.rs` `auto_update`) will still offer upstream releases; accepting
  one replaces the control-mode patch series. Do not accept in-app updates on a
  fork build (section 0 already warns about `herdr update`).

**Implement**
1. [x] `build_and_install.sh`: tool preflight (`brew`+`perl` on macOS; `xz` on
   Linux; `cc`, `curl`, `tar` everywhere) with "missing required tool: X"
   messages; rustup if no `rustup`; macOS: `brew install zig@0.15` (no
   auto-update) + patched lib copy (stale `.tmp` removed first, built in
   `.tmp`, then `mv`) + wrapper; Linux: official tarball extracted into a
   `mktemp` dir with an EXIT trap, then `mv`; `cargo build --release --locked`;
   smoke-test `target/release/herdr --version` BEFORE touching the install;
   install to `.herdr.new` and `mv` (an interrupt between the two leaves a
   dotfile `.herdr.new` that cannot shadow `herdr` and is overwritten next run);
   PATH: fish universal var whenever a fish config exists, AND the `$SHELL` rc -
   zsh `~/.zshrc`, bash
   `~/.bash_profile`-or-existing-`~/.profile` on macOS / `~/.bashrc` on Linux,
   otherwise print the export line; exact-line duplicate guard; skipped when
   already on PATH.
2. [x] Config install (2026-08-23): `herdr.config.toml` at the repo root is the
   fork's config template; the script renders it to herdr's config path
   (`HERDR_CONFIG_PATH` > `XDG_CONFIG_HOME` > `~/.config`, same precedence as
   `src/config/io.rs`) with `@DEFAULT_SHELL@` replaced by an absolute path
   resolved on the installing machine (`command -v fish`, else empty so herdr
   falls back to `$SHELL`). Motivation: the owner's `~/.config/herdr` was copied
   Mac -> Linux with `default_shell = "/opt/homebrew/bin/fish"`; every pane spawn
   failed, restore dropped all workspaces, and `ensure_default_workspace`
   (src/app/mod.rs:1183, ticked from src/server/headless.rs:667) retried every
   250 ms forever - the "stuck with no space" report. Only `config.toml` is
   written; session.json, logs, sockets, release notes, plugin lock, and
   agent-detection overrides are never read or copied. The rendered file is
   validated with `herdr config check` (exits 1 on diagnostics) before it can
   replace anything; an unchanged render is a no-op, a differing existing file is
   kept as `config.toml.bak`; a running server gets `server reload-config`
   best-effort; template popup commands missing from PATH print a note.
   Verified by a stub-cargo sandbox harness (fresh home, rerun no-op, user-edited
   config backed up, fish absent -> empty default_shell, broken template ->
   exit 1 with existing config untouched and no `.config.toml.new` left) and by
   a real run on the Gentoo host (`/usr/bin/fish` rendered, server reloaded).

**Stress-test strategy (how to test without touching the real system)**
- Linux: Docker containers from clean images, script copied in and run as a
  fresh user would (`debian:bookworm-slim`, `fedora:latest`; `--platform
  linux/amd64` available via emulation for the x86_64 URL path). Vary what is
  preinstalled (no curl, no cc, no xz) to exercise the preflight. The 2 GB
  Docker cap kills the final `rustc` of the herdr crate (2.1 GB peak RSS), so
  the install/PATH half is exercised with a stub `~/.cargo/bin/cargo` that
  checks `$ZIG` and emits a fake `target/release/herdr` - real zig download,
  real extraction, real install, real rc edits.
- macOS (no containers): the real-system risks are the zig cache mirage, the
  live `~/.local/bin/herdr`, and the shell rc files. Run the full script only
  with fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`; test the PATH,
  install, and zig sections in isolation by extracting them into a throwaway
  `$HOME`/`DATA_DIR`/cwd with stub `cargo` and stub artifacts. A fake `$HOME`
  is NOT valid for the full build (rustup, cargo, and zig all key off it). Gold
  standard for the cold path: a throwaway macOS user (`sysadminctl -addUser`,
  needs sudo) or a Tart VM.

**Verify**
- [x] macOS with brew zig and rustup already present, fresh zig caches: full
      run builds libghostty from scratch (1m17s), installs, `herdr --version`
      ok; rerun idempotent. This is NOT cold-machine coverage (see open item).
- [x] Live-install gate: with a stub `cargo` producing a `target/release/herdr`
      that exits 1, the build+install section exits 1 and the pre-existing
      install still runs; with a good artifact it is replaced and no
      `.herdr.new` remains.
- [x] Zig section: a pre-existing `zig-lib-*-patched.tmp` (interrupted copy)
      no longer traps the rerun; the patched header is present; rerun no-op.
- [x] PATH section, both directions: a `$SHELL=/bin/zsh` user with a
      `~/.config/fish` dir gets BOTH `fish_user_paths` and a `~/.zshrc` line
      (rerun: still one of each); a `$SHELL=fish` user gets `fish_user_paths`
      only and no `.zshrc`/`.bash_profile`; a `$SHELL=fish` user whose fish
      config lives under a custom `XDG_CONFIG_HOME` still gets `fish_user_paths`
      (the check mirrors line 18's `${XDG_...:-default}` form); a zsh user with
      no fish dir gets `.zshrc` only. If `fish -c` itself fails (read-only
      `fish_variables`, fish < 3.2) `set -e` stops before the `$SHELL` rc is
      edited - accepted, no error handling added. zsh appends once (exact-line guard: a pre-existing
      `.local/bin/other` line no longer suppresses it); bash on macOS appends
      to an existing `~/.profile` and creates `~/.bash_profile` only when
      neither exists; unknown shell prints the hint; reruns no-op.
- [x] Linux preflight: debian without a compiler stops at
      "missing required tool: cc" (no mid-script `command not found`).
- [x] Linux stub-cargo harness, debian:bookworm-slim (stub `~/.cargo/bin/cargo`
      checks `$ZIG`, emits a fake artifact): full script path twice - real zig
      fetch, EXIT-trap leaves no `.zig-*` dir, install + atomic replace,
      `~/.bashrc` gains exactly one line, second run is a no-op, exit 0 both.
      Same harness on `fedora:latest` as a `$SHELL=/usr/bin/zsh` user who had
      run `fish -c true` once: `~/.zshrc` one line AND `fish_user_paths` set
      (both directions of the M5 case), no `.zig-*` leftovers, exit 0 twice.
- [ ] Linux end-to-end compile (debian + fedora) once Docker Desktop memory is
      raised to >= 4 GB (user setting); everything up to the final rustc is
      already green on both. Alpine/musl is a NON-GOAL per the intent record
      (earlier runs built identically up to the same point; not supported).
- [ ] macOS cold path (no rustup, no brew zig, no `~/.local/bin`) - unverified;
      needs a throwaway macOS user or a Tart VM. [needs a human or sudo]
- [x] Adversarial loop via keemakr-long-yolo-harden-plan
      (`adv_convo_1787423967261/`): CONVERGED in round 4 (2026-08-23), both
      judges agreeing.

**Round log (adv_convo_1787423967261)**
- r1: 1 BLOCKER (smoke test ran after the live install was overwritten), 4 MAJOR
  (`.tmp` copy trap, distro cargo bypassing the toolchain pin, `$SHELL`
  misdetecting fish, `[x]` overstating macOS coverage), 11 MINOR, 4 NIT - all
  accepted; fixes verified by stub-cargo harnesses on both sides.
- r2: 1 MAJOR (the fish fix inverted: a fish dir proves only that fish ran once -
  now add to fish AND edit the `$SHELL` rc), 1 MINOR (`need cc` is a shim on
  macOS; plan text corrected), 3 NIT - accepted.
- r3: 1 MAJOR (fish check ignored `XDG_CONFIG_HOME`; one token) - accepted.
- r4: all closed by the adversary's own re-runs; CONVERGED.

**Accepted execution order for the open items**
1. macOS cold path (no rustup, no brew zig, no `~/.local/bin`) via a throwaway
   macOS user (`sysadminctl -addUser`) or a Tart VM - before pointing any fork
   user at the script; it is the only residual that costs a stranger real time.
2. Linux end-to-end compile (debian + fedora) once Docker Desktop memory is
   raised to >= 4 GB; lower priority - the stub harness covers everything but
   rustc's peak RSS and upstream CI compiles herdr on Linux every run.
3. Owner ruling on `~/.local/share/herdr` as the toolchain home (currently a
   PROPOSAL the script has committed to).

**Residual-risk register (the live list; nothing below blocks running the
script on the owner's Mac today)**
1. macOS cold path never executed as a composition (highest).
2. Linux end-to-end compile never completed on this host (2 GB Docker cap).
3. `need cc` asserts nothing on macOS; CLT coverage rides on `need brew`.
4. brew `zig@0.15` is deprecated 2027-04-15 / disabled 2028-04-15; the macOS
   branch dies then unless herdr has moved to zig 0.16 (herdrdev/herdr#285).
5. No checksum on the zig tarball (recorded decision; TLS + xz integrity).
6. 209 MB per zig version accumulates under `~/.local/share/herdr`; manual prune.
7. `fish -c` failure aborts before the `$SHELL` rc edit; an interrupt between
   `install` and `mv` leaves a `.herdr.new` dotfile - both documented, no code.
8. PATH-membership test is a literal substring match; a differently spelled
   entry leads to a harmless duplicate (over-adding is cheap).
9. herdr's in-app updater will offer upstream releases over a fork build -
   human discipline, not script.
10. "Replacing a running binary leaves the process intact" was verified with
    `/bin/sleep`, not a live herdr from the target path; safe by construction
    (`mv`), noted so the checkbox is not read as stronger than it is.
11. `~/.local/share/herdr` is a PROPOSAL, not a ruling.
12. Invoking the script through a symlink resolves the symlink's directory, not
    the repo (NIT, unfixed by choice).
13. Config install prefers fish when it is on PATH (the template is tuned for
    it); a fork user who has fish installed but does not use it gets fish panes
    until they edit `default_shell`. `herdr config check` does not verify that
    `default_shell` exists, so the script's `-x` test is the only guard.
14. `config.toml.bak` holds one generation only; a second differing render
    overwrites the previous backup.
Convergence is NOT authorization to spend or ship; owner decisions (items 1-3
of the order) stay in their own queue.

### Phase 9 - Upstream sync onto the client-rendered shell (2026-10-07)

**What moved upstream**: 460 commits from `10974c82` to `a124eed7` (v0.9.x).
`207be3c7 refactor: render the shell in the client (#3487)` deleted
`src/app/input/*`, `src/ui/menus.rs`, and `src/ui/keybind_help.rs`; input
routing, mode bars, and help now live in the client (`src/client/shell/`,
`src/input/`), and every action is an endpoint API method. A mechanical rebase
was impossible, so the feature commit was re-implemented on a fresh branch
(`sync/upstream-2026-10-07`) and the docs/build commits replayed unchanged.
Upstream also moved the vendored libghostty-vt build to zig 0.16.0.

**Mapping (old -> new)**
- `Mode::Control` + `AppState.control_scope` -> `ClientShellMode::Control(ControlScope)`
  (`src/client/shell/state.rs`); the scope rides in the mode so the mode bar
  and input-lease context see it without an extra field.
- `handle_control_key` / `control_action_for_key` / sticky set ->
  `src/client/shell/control.rs` (`route_control_key`, same precedence: prefix
  chains, scope letters, then esc/enter/entry toggle, then verbs).
- `NavigateAction::{MoveTab*, MoveWorkspace*, Enter*Mode}` ->
  `KeybindAction` variants (`src/input/keybindings.rs`), resolved to
  `tab.move` / `workspace.move` / `workspace.move_block` in
  `endpoint_method_for_action`; workspace moves reuse the drag path's
  `workspace_move_method` over sidebar root entries.
- `render_control_overlay` -> `control_mode_segments` in
  `src/client/shell/render.rs`. The bottom-tab-bar mouse guard is gone: the
  composer already clears tab hits when a mode bar replaces the tab row.
- Help group -> `src/input/keybind_help.rs`. Remote-profile round-trip test ->
  `src/config.rs` (`parse_client_keybindings` no longer exists).
- Config layer (`model.rs`, `keybinds.rs`, `main.rs` template, reference JSON,
  en/ja/zh-cn docs) merged three-way; the `docs/next/CHANGELOG.md` entry was
  dropped because upstream now curates the changelog only at release time.

**Decisions**
- Upstream added `move_tab_previous` / `move_tab_next` (#2561), which WRAP.
  Ours stay as `move_tab_left` / `move_tab_right` and stop at the edges (the
  no-wrap decision in section 5); both coexist. RULED (owner, 2026-10-07):
  ours are the fork's tab-move keys; upstream's stay unbound (default) and
  untouched in code so future syncs do not conflict over them.
- Zig: 0.16.0 includes the Mach-O arm64e TBD fix (ziglang/zig#31673, merged
  2026-03-27; 0.16.0 released 2026-04-13) and macOS 26.4 headers, so
  `build_and_install.sh` fetches the official tarball on both OSes. This
  retires Phase 8 residuals 4 (brew zig@0.15 deprecation) and the patched
  libcxx copy.

**Verify**
- [x] fmt + `clippy --all-targets -D warnings` clean.
- [x] nextest: 3973 tests, all green. `integration_commands_run_locally_when_server_is_missing`
      fails only when the shell exports `CLAUDE_CONFIG_DIR` (the test fakes
      `HOME` but not that variable); passes with it unset. Pre-existing upstream.
- [x] `just maintenance-test`, `ui-hot-path-architecture-test`,
      `integration-assets-test`, `docs-contract-test` green (config-reference
      parity included).
- [x] 23 new/ported unit tests (`client::shell::tests::control_modes`, help
      group, keybind parsing/conflicts, profile round-trip).
- [x] Headless end-to-end (release binary, isolated XDG root, all `HERDR_*`
      stripped, live server untouched): 47/47 checks with the fork's
      `herdr.config.toml` rendered as the config - every mode entry, verbs,
      sticky vs leaving actions, no-wrap edges, worktree-free workspace moves,
      scope hops, prefix chaining, toggle-off, alt+i/o, auto-split direction,
      zoom toggle, detach/reattach persistence, clean shutdown.
- [x] `build_and_install.sh` cold run under a fake `HOME` (real rustup caches,
      `HERDR_*` stripped): zig 0.16.0 fetched, release built and smoke-tested,
      installed, template rendered with `default_shell = "/usr/bin/fish"` and
      passed `config check`, fish_user_paths set; reruns idempotent; a bash
      user gets exactly one `.bashrc` line.
- [ ] `just windows-lint` not run (no xwin SDK on this host).
- [ ] macOS build with the official zig 0.16.0 tarball not exercised here.
- [ ] Manual keyboard feel on a real terminal. [needs a human at the keyboard]

### Phase 10 - Agent variants and kept launch args (2026-10-07)

**Why**: `claude-kee` and `claude-me` are fish functions that only change
`CLAUDE_CONFIG_DIR` (separate logins, shared session store via symlinks, see
`~/.local/share/claude-accounts/share-sessions.py`). Herdr restored every Claude
pane as `claude --resume <id>`, so kee panes came back in the wrong account and
lost `--dangerously-skip-permissions`; the sidebar could not tell them apart.

**Design**: `[session] agent_variants` (agent, name, env match) and
`resume_keep_args` (per agent; trailing `=` marks a value flag). On an applied
`pane.report_agent_session` without a self-reported `resume_argv`, and again
when process detection newly acquires an agent with a known session, the
server reads the agent process's environment (`platform::process_environ`,
Linux /proc behind the remote-read guard, macOS KERN_PROCARGS2) and argv, then
records `ReportedAgentResume` = built-in plan with the variant as command and
kept args after it (`agent_resume::launch_profile`), and sets a display-only
`display_agent` label under the official source. No match and no kept args
drops a resume this source set earlier, so the last-used launch always wins.
No API or wire change; restore already prefers reported resume commands.

**Verify**
- [x] Unit: launch_profile matching, `~/` expansion, empty-means-unset, value
      flags, invalid names rejected; full suite green (one load-sensitive
      timing test passes 3/3 in isolation).
- [x] E2E (isolated herdr, real fish + Claude, 44/44): one session hopped
      claude-kee+bypass -> claude-me -> claude+bypass -> claude-kee, each hop
      restored after a server restart in the right config dir, with the flag
      exactly when it was launched with it (argv and Claude's own UI), labeled
      in herdr, and remembering a codeword from the first turn.
- [ ] Upgrading the live 0.8.0 server needs a stop (pre-generation-1, no
      handoff); `~/.local/share/claude-accounts/migrate-herdr-resume.py`
      captures variants from the live processes and patches the final
      snapshot so the first restore is already correct.

### Phase 11 - Live deployment and account migration [HARDENED 2026-10-07, adv_convo_1791387860515]

**Goal**: move the live void-workstation herdr (release `20260906`, herdr
0.8.0) to the fork build `fb11df79` (0.9.3, staged at
`~/.local/share/herdr/staged/herdr-fb11df79`; Phase 12 replaced the
original `e897ed0e`) so that every Claude pane comes
back in its own account, with its permission bypass exactly when it had one
(either `--dangerously-skip-permissions` or `--permission-mode
bypassPermissions`), and the same conversation. Intent: research/intent.md
"Claude accounts, herdr agent variants, live deployment". Pane and agent counts
are never hard-coded: every expectation is derived from the capture (A6).

**Already in place (verified 2026-10-07, not part of this phase)**
- Shared session store: `~/.claude/{projects,file-history,session-env,tasks,
  todos,plans,paste-cache}` are symlinks into `~/.claude-keemakr/`; logins are
  per dir. Script + backup in `~/.local/share/claude-accounts/`.
- fish: `conf.d/claude-accounts.fish` defines only `claude-kee`/`claude-me`.
- Fork features: Phase 9 modes (e2e 47/47), Phase 10 variants (e2e 44/44).
- `herdr.config.toml` keeps `["--dangerously-skip-permissions",
  "--permission-mode="]` (A1: 11 live kee panes use the second form).

**Constraints**
- C1. 0.8.0 predates the client endpoint generation (`207be3c7`, 2026-09-01),
  so live handoff does not apply; the upgrade is stop -> start, which ends every
  pane process. Restore then relaunches agents from the snapshot.
- C2. The old server never recorded variants or launch flags; its snapshot has
  `agent_session` per pane but no `agent_resume`. Without migration every
  Claude pane restores as `claude --resume <id>` (personal account, no bypass).
- C3. The operator (this Claude session) runs inside pane `wY:p1`; anything it
  starts in its pane dies with the server unless it leaves the pane's session.
- C4. The release dir also carries helix (`bin/hx`, `runtime/`, 2.3 GB);
  `promote.sh` hardcodes `20260906`.
- C5. Nested `claude` runs started inside a Claude pane inherit
  `HERDR_PANE_ID`, and their SessionStart hook overwrites that pane's session
  record (happened during testing; corrected by re-reporting `wY:p1`).
- C6 (A2). Panes inherit the server's environment minus a few CLAUDE_CODE_*
  keys (`src/pane.rs` `apply_pane_launch_env`), so `CLAUDE_CONFIG_DIR`,
  `HERDR_PANE_ID`, `CLAUDE_EFFORT` etc. of whoever starts the server reach
  every pane. The operator's env has `CLAUDE_CONFIG_DIR=~/.claude-keemakr`; the
  live server's (`/proc/<pid>/environ`) has no CLAUDE_* or HERDR_* except
  `HERDR_STARTUP_CWD`. The new server must start with the old server's env.
- C7. An attached 0.8.0 client exits when its server stops and does not
  autostart one (probed on an isolated 0.8.0 server); only a newly typed
  `herdr` would autostart a server.
- C8. A 0.9.3 snapshot is version 3, readable by 0.8.0 (probed: 0.8.0
  restored all workspaces from a snapshot 0.9.3 wrote).

**Implement (`~/.local/share/claude-accounts/deploy-herdr.sh`, subcommands
`dry-run`, `deploy`, `rollback`; every herdr call by absolute path)**
Every root the script touches is a variable whose default is the live value
(B2): `BIN_DIR` (`~/.local/bin`), `VW_BASE` (`~/.local/share/void-workstation`),
`HERDR_CFG` (`~/.config/herdr`, socket `$HERDR_CFG/herdr.sock`), `WORK`
(`~/.local/share/claude-accounts`). The script never derives a path from
`HERDR_SOCKET_PATH` or any inherited `HERDR_*`. `relink()` re-creates
`$BIN_DIR/herdr -> $VW_BASE/current/bin/herdr` atomically (`ln -s` + `mv -T`)
whatever is there; the lock stub carries the marker line
`# herdr-deploy-lock`, and the generalized promote replaces a file with that
marker without archiving it (B1). Every herdr CLI call and the server start run
through one wrapper that sets `HERDR_SOCKET_PATH=$HERDR_CFG/herdr.sock` and
`XDG_CONFIG_HOME=$(dirname $HERDR_CFG)` and unsets `HERDR_PANE_ID`, so the
socket a call reaches is the one the variables name, never the CLI's default
(finding C2(r3)).
Before anything stops:
1. Stage release `releases/20261007`: `cp -al releases/20260906`, then
   install the staged binary as a new inode at `bin/herdr` (the old release is
   untouched). Render the new config (template, `@DEFAULT_SHELL@` ->
   `/usr/bin/fish`) to the deploy dir.
2. Preconditions, abort with nothing stopped (every abort before step 6 runs
   `relink()` and exits; B1): new binary `--version` = 0.9.3;
   `herdr config check` of the rendered config via `HERDR_CONFIG_PATH` with
   the new binary; `~/.local/bin/claude` resolves; old server pid = the
   process listening on `~/.config/herdr/herdr.sock`; for every live Claude
   pane the registry session id equals the server's `agent_session`
   (`herdr pane get`). This review's manifest is terminal and its watchdog
   has exited (no late nudge typed into a restored pane), then the adversary
   pane of this review is closed.
3. Save `/proc/<old server pid>/environ` (C6) and back up
   `~/.config/herdr/config.toml`.
4. Lock: replace `~/.local/bin/herdr` with a stub that prints "herdr upgrade
   in progress - wait for DONE in <log>" and exits 1 (A4, C7).
5. Capture last (A3): `HERDR_CONFIG_PATH=<rendered config>
   HERDR_LIVE_SOCKET=$HERDR_CFG/herdr.sock migrate-herdr-resume.py capture
   <capture.json> $HERDR_CFG/session.json`, keyed by pane id. It exits non-zero
   unless the captured pane set equals the Claude panes in the server's own
   snapshot (finding C1(r3): an empty or short capture cannot pass) and on any per-pane
   bypass mismatch between `/proc` and the keep list (A1 oracle) -> relink and
   abort, nothing stopped. Then assert the pid listening on
   `$HERDR_CFG/herdr.sock` is still the pid saved in step 2 (finding C2(r3)).
From here on every failure runs `rollback` automatically:
6. `herdr server stop` (old binary); wait until the old pid is gone and
   `session.json` stopped changing; copy it as `session.final.json`.
7. `migrate-herdr-resume.py apply` on `~/.config/herdr/session.json`, keyed
   by pane, using the snapshot's final session ids. A Claude pane without a
   capture entry loses its `agent_session` (no wrong-account restore); the log
   and DONE banner print its session id and cwd with the variant marked
   UNKNOWN, never a plain `claude --resume` (finding C1(r3)).
8. Install the rendered config; promote `current` -> `releases/20261007` (a
   generalized `promote.sh <release>`), which also restores the real
   `~/.local/bin/herdr` symlink (lock off).
9. Start the new server detached with the saved environment:
   `setsid -f env -i <saved env> <release>/bin/herdr server`.
10. Verify against the capture, polling until every captured pane has its
    Claude process (`startup_per_agent_delay` spaces the resumes) or a timeout
    reports the rest: the server listening is a new pid running
    0.9.3; every captured pane has one Claude process whose
    `CLAUDE_CONFIG_DIR` and bypass match the capture and whose argv ends in
    `--resume <its final id>`; `wY:p2`-style plain panes have no
    `CLAUDE_CONFIG_DIR`; a fresh shell pane has no CLAUDE_* and no
    `HERDR_PANE_ID` but its own. Per-pane mismatch: report with that pane's
    manual command (not a rollback: rolling back loses every variant).
    Server-level failure (no new server, wrong version): `rollback`. The
    fresh shell pane used for the env check is closed before DONE.
11. Regenerate fish completions; print DONE with the report. The owner
    reattaches with `herdr` only after DONE.
The operator launches `deploy` with `setsid -f`, output to
`~/.local/share/claude-accounts/deploy-<ts>/log`, so it survives step 6 (C3).

**Rollback (`deploy-herdr.sh rollback`, automatic after step 6, or by hand)**
First establish that no herdr server is alive (B3): the old pid gone and
nothing listening on `$HERDR_CFG/herdr.sock`; a stray server is stopped with
its own binary (`/proc/<pid>/exe`), and if one still listens rollback refuses
and prints why. Then switch `current` back to `releases/20260906` and run
`relink()` (the stub may still be there when rollback fires before step 8; B1),
restore the backed-up `config.toml` with `[session] resume_agents_on_restore =
false` added, restore `session.final.json` (the old server's own last save),
start 0.8.0 detached with the saved environment, and print every captured
pane's manual command (`<variant> <kept args> --resume <final id>`, cwd) so
the owner restores accounts and bypass by hand; 0.8.0 cannot do it (C2).

**Verify (gates)**
- [x] G0 (A1, A3): pane-keyed capture + apply on a copy of the live snapshot:
      every live Claude pane captured, bypass oracle clean, all patched.
- [ ] G1 `dry-run`: steps 1-5 with nothing stopped, lock released; prints the
      per-pane plan and exits 0.
- [x] G2 detachment (C3): a `setsid -f` child started from a pane of an
      isolated 0.8.0 server survived that server's `server stop`. Repeat with
      the launch shape the operator uses (a non-interactive child of a Claude
      Bash tool) before deploy.
- [ ] G3 rollback rehearsal (B2): all four roots under `/tmp/claude-1000/a<short>`
      (a copy of the release with hardlinks, a copy of the live config and a
      fake-id copy of the snapshot); the isolated old server is started with
      a copy of the live server's environ (XDG redirected); the script runs
      from the operator's own env (real `CLAUDE_*` present, only `HERDR_*`
      unset). Asserts: (a) `deploy` - the new server's environ and a fresh
      shell pane have no `CLAUDE_CONFIG_DIR` and no foreign `HERDR_PANE_ID`;
      (b) `rollback` after `deploy` - 0.8.0 serving, no agent auto-resumed,
      manual commands printed; (c) a failure injected at step 7 with the stub
      in place - `readlink $BIN_DIR/herdr` is the release symlink and
      `$BIN_DIR/herdr --version` prints 0.8.0; (d) the live
      `readlink ~/.local/bin/herdr`, `readlink current` and live server pid
      are identical before and after G3, and before G3's step 6 the pid
      listening on its `$HERDR_CFG/herdr.sock` is asserted not to be the live
      server's (finding C2(r3)).
- [x] G5 short-capture refusal (finding C1(r3)): `capture` with the socket left to its
      default (deploy dir) exits 1 naming every snapshot Claude pane it did
      not capture; with `HERDR_LIVE_SOCKET` set it captures 16 of 16 and exits 0.
- [ ] G4 live: step 10's report is clean; this session resumed in `wY:p1`;
      sidebar labels show variants.

**Hardening record (adv_convo_1791387860515; adversary claude/claude-opus-5-5/high
as claude-kee; judge same tuple; converged round 4, both judges agree on sha
dd621f39)**
- Round 1: A1 BLOCKER 11 kee panes use `--permission-mode bypassPermissions`,
  not kept -> keep list + independent bypass oracle. A2 BLOCKER new server
  would inherit the operator's `CLAUDE_CONFIG_DIR` -> `env -i` with the old
  server's environ. A3 MAJOR session-id keyed capture and post-stop abort ->
  pane-keyed, capture last, never fall back to `claude --resume`. A4 MAJOR
  owner reattach race -> lock stub + DONE + new-pid check. A5 MAJOR rollback
  was prose -> executable `rollback`. A6/A7 MINOR.
- Round 2: B1 MAJOR stub survived early rollback -> `relink()` + marker-aware
  promote. B2 MAJOR rehearsal targeted live paths -> parameterized roots, G3
  isolation asserts. B3 MINOR rollback could start a second server -> guard.
- Round 3: C1(r3) BLOCKER capture with the default socket matched zero panes
  and passed -> explicit `HERDR_LIVE_SOCKET` + snapshot-derived expected set
  (G5). C2(r3) MAJOR CLI calls fell back to the live socket in G3 -> one wrapper
  sets the socket and XDG for every call.
- Round 4: CONVERGED.

**Accepted execution order**: (1) pre-deploy gates on isolated roots: G2 repeat
in the operator's launch shape, G3 (a)-(d), then G1 `dry-run` on live roots
(nothing stops); (2) close the review (manifest terminal, watchdog exited,
adversary pane closed); (3) `deploy` detached, steps 1-11, `rollback` on any
failure from step 6; (4) owner reattaches only after DONE, then G4.

**Residual register (accepted)**
- R1 a rollback leaves accounts and bypass to the owner (printed commands).
- R2 livelock: a pane holding `agent_session` after its Claude exited, or a
  Claude started after the last save, makes step 5 refuse until settled.
- R3 a variant change between step 5 and step 6 restores the captured variant
  (seconds; lock already in place).
- R4 integration hook stays v7 vs shipped v10: works, shows an "outdated
  integration" badge; reinstalling is the owner's call.
- R5 (folded) step 10 polls and closes its probe pane.

### Phase 12 - pi, codex, and the untested angles [HARDENED 2026-10-07, adv_convo_1791389526754]

**Why**: Phases 10-11 only cover Claude. On this machine herdr's codex and pi
integrations are NOT installed (`herdr integration status`: `codex: not
installed`, `pi: not installed`), so herdr has no session id for them: the live
codex pane `wS:pW` (`codex -m gpt-6-astra -c model_reasoning_effort=high
--search --dangerously-bypass-approvals-and-sandbox`, cwd
`~/Work/Keemakr 2.0/covalent`) would come back from any restart as a bare shell.
Several Claude angles were never exercised either.

**Facts (verified 2026-10-07)**
- codex-cli 0.159.2. `codex resume [OPTIONS] [SESSION_ID]` accepts `-m`, `-c`,
  `--search`, `--dangerously-bypass-approvals-and-sandbox`, `-s`, `-a`, `-p`
  as its own options. `~/.codex/config.toml` already pins `model`,
  `model_reasoning_effort = "high"`, `approval_policy = "never"`,
  `sandbox_mode = "danger-full-access"`.
- A running codex is a node wrapper (pgid leader, full argv) plus the native
  `codex` (comm `codex`) holding exactly one rollout fd
  `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` and one
  `thread-writer-locks/<uuid>.lock`; the uuid is the session `codex resume` takes.
- codex 0.159 runs newly installed or changed hooks only after the owner trusts
  them (modal "Hooks need review": "Trust all and continue" / "Continue without
  trusting"); trust persists as `hooks.state.<...>.trusted_hash` in config.toml.
  `herdr integration install codex` writes `hooks.json` + script and appends
  `[features] hooks = true`; it has no trust handling.
- pi 0.84.3 runs via `~/.local/bin/pi` (fish: `exec node .../pi-080/.../cli.js`),
  and `cli.js:11` sets `process.title`, which wipes `/proc/<pid>/cmdline` to
  `pi` (probed): herdr cannot read pi's launch flags from /proc. `~/.pi/agent`
  is a git repo with 15+ owner extensions; some extensions read the live
  `auth.json` and write live files regardless of `PI_CODING_AGENT_DIR`.
- codex `auth.json` refresh tokens are single use: a copied CODEX_HOME that
  refreshes logs the owner's real codex out.

**Decisions**
- D1 never start a real codex or pi against copied credentials; every rehearsal
  uses stubs (G12.2). Live checks after install are file-level.
- D2 codex hook trust is given once by the owner, interactively, on the first
  codex start after install. `--dangerously-bypass-hook-trust` is NOT used
  (a new dangerous flag needs an owner ruling).
- D3 pi's flags are known only inside pi: the fork's pi integration asset
  reports `resume_argv` itself, built from `process.argv` with its own
  allowlist (`--model`, `--thinking`, `--provider`, `--approve`/`-a`) plus
  `--session <path>`; herdr config has no `resume_keep_args.pi` (the server
  resolver then stays out of pi's way: no keep list, no variant). A future pi
  `agent_variant` must not replace a self-reported resume (the resolver would
  rebuild it from the wiped `["pi"]` argv).
- D4 `-c`/`--config` values are not kept (they would land in the 664
  `session.json` and may carry secrets); codex overrides belong in
  config.toml or a `-p` profile. `--worktree` and `--remote` are never kept.
  So the restored `wS:pW` argv differs from the live one by design: expected
  exactly `codex resume -m gpt-6-astra --search
  --dangerously-bypass-approvals-and-sandbox <id>` (effort comes from
  config.toml).
- D5 `server reload-config` changes resume resolution from each pane's NEXT
  session report or detection onward; existing panes keep their recorded
  command until then (documented).

**Implement, in this order**
1. Code: (a) kept args go after a leading subcommand word (codex:
   `codex resume <kept> <id>`; claude/pi unchanged); (b) a launch-resolved
   resume dedupes on the session, not argv; (c) resolution also runs when a
   state report (`pane.report_agent`) first establishes a session (A8);
   (d) the fork's pi asset sends `resume_argv` per D3. Unit tests per change.
   1(c) resolves once per newly established session, never per state report
   (`UserPromptSubmit`/`Stop` arrive every turn and resolution reads /proc).
2. Build and stage `herdr-<newsha>`; re-run the Phase 10 e2e, the migration
   rehearsal and Phase 11 G3 against it; Phase 11 deploys `<newsha>` instead
   of `e897ed0e` (Phase 11 binary references updated).
3. Config template: `resume_keep_args.codex = ["--dangerously-bypass-approvals-and-sandbox",
   "--search", "--no-alt-screen", "-m=", "--model=", "-s=", "--sandbox=", "-a=",
   "--ask-for-approval=", "-p=", "--profile=", "--add-dir=", "-C=", "--cd=",
   "--enable=", "--disable="]`; rendered before the Phase 11 capture.
4. Migration (Phase 11 steps 5/7/10, rollback) extended to codex: the expected
   codex set comes from the live server, read-only (`herdr pane list`,
   `agent == "codex"`), and capture refuses unless every expected pane yields
   exactly one rollout + one writer-lock fd with matching uuids (taken from
   the lock name); codex capture runs last; apply ADDS `agent_session {source
   herdr:codex, agent codex, kind id}` + `agent_resume` to that pane; the
   report and rollback print `codex resume <kept> <id>` with cwd for every
   codex pane. Just before the new server starts (after step 9's predecessor
   steps), the deploy polls until the captured codex pids are gone, with a
   timeout: on timeout the deploy drops that pane's codex `agent_session` and
   `agent_resume`, prints its manual `codex resume ...` command, and STILL
   starts the new server (never halts serverless, never `rollback`); step 10
   re-checks and records `codex --version`.
5. Integrations, inside the Phase 11 deploy after apply and before the new
   server starts: back up `~/.codex/config.toml`, `~/.codex/hooks.json` (absent
   today) and `~/.pi/agent/extensions/`; `herdr integration install codex` and
   `... pi` with the new binary. The restored `wS:pW` therefore opens on the
   hook-trust modal: the DONE banner tells the owner to choose "Trust all and
   continue". `herdr-agent-state.ts` is an untracked file in the `~/.pi/agent`
   git repo; committing it is the owner's call. An install failure is never
   fatal: it is logged, listed in the DONE banner with its manual
   `herdr integration install <x>` command, and never triggers `rollback`
   (codex tracking then starts after that manual install).
6. Claude angles, isolated, no model call, nothing touching live
   conversations: in-session `/clear` and `/resume <id>` move the recorded
   resume to the new id; `claude-me`'s `/resume` picker lists a session made by
   `claude-kee`. Every session used is a throwaway created under a
   `/tmp/claude-1000/a...` cwd, asserted absent from the live snapshot's
   `agent_session` set, and deleted with its project dir afterwards (A6).

**Verify (gates)**
- [ ] G12.1 unit: kept-arg placement for claude, codex, pi; session dedupe for
      two variants; resolution on a first state-report session and NOT on a
      second report for the same session; `launch_profile` on the live codex
      argv shape returns exactly the D4 string, and the migration script's
      codex capture of the same argv returns the identical argv (no rewrite
      on first detection).
- [ ] G12.2 isolated e2e with stubs (D1): stub `codex` and `pi` first on the
      isolated server's PATH. The codex stub records argv and holds an open
      fake rollout + writer lock; the real installed codex hook script, fed a
      synthetic SessionStart, reports it. The pi stub sets `process.title="pi"`
      (reproducing the /proc wipe) and loads the fork's pi extension with a
      fake ctx. Asserts: saved resume `codex resume <kept> <id>` and
      `pi <kept> --session <path>`; after restart the stubs record exactly those
      argv.
- [ ] G12.3 migration rehearsal including the live codex pane (fake ids):
      codex pane gets `agent_session` + `agent_resume` equal to the D4 string;
      a capture with the codex pane hidden refuses; an injected integration
      install failure (invalid pre-existing `hooks.json` in the isolated
      CODEX_HOME) still ends in DONE on the new server.
- [ ] G12.4 Claude angles of step 6.
- [ ] G12.5 live, after deploy: integration files present, owner pi extensions
      byte-identical to the backup, `~/.codex/hooks.json` valid, after the
      owner's trust `hooks.state` holds the herdr hook, `wS:pW` resumed with
      exactly the D4 argv and its conversation.

**Residual (accepted)**
- macOS; `herdr --remote`; concurrent use of one session in two accounts; a
  Claude update adding an unshared per-session dir; a variant-less custom
  `CLAUDE_CONFIG_DIR` restoring in the default account.
- If the owner picks "Continue without trusting", codex panes keep the
  migration's recorded session until trust is given; in-codex `/new` or
  `/resume` stays invisible to herdr until then.
- An npm `codex` update between rehearsal and deploy can change hook or resume
  behavior; the report records `codex --version`.

**Hardening record (adv_convo_1791389526754; adversary claude/claude-opus-5-5/high
as claude-kee; judge same tuple; converged round 3, both judges agree on sha
fac8aef3)**
- Round 1 (6 MAJOR, 4 MINOR): pi wipes its argv via `process.title` -> pi
  asset reports `resume_argv` (D3); codex hook trust gate -> owner trusts once
  (D2); rehearsal with copied credentials could log codex out -> stubs only
  (D1); codex capture had no independent expected set -> live `pane list` +
  fd uuid checks; deploy binary/order undefined -> explicit order on a new
  build; Claude angle tests could touch live conversations -> throwaway
  sessions; MINOR: reload semantics (D5), first state-report resolution,
  `-c` secrets (D4), keep-list gaps.
- Round 2 (1 MAJOR, 3 MINOR): integration install failure inside the rollback
  window -> non-fatal; exact expected codex argv; codex-pid poll moved before
  server start; script/server argv equality and once-per-session resolution.
- Round 3: CONVERGED, condition folded into step 4 (poll timeout never halts).

**Accepted execution order**: 1(a)-(d) + G12.1; build `<newsha>` and re-run
Phase 10 e2e, G12.3, Phase 11 G3, update Phase 11 references; G12.2 (stubs);
G12.4 (throwaway Claude sessions); render the codex keep list before capture;
Phase 11 deploy of `<newsha>` (apply Claude + codex, non-fatal installs,
codex-pid poll, start); owner trusts hooks in `wS:pW`; G12.5.

**Residual register (accepted)**: as listed above, plus hook trust may be asked
again when a reinstall changes the hook config; whether codex fires SessionStart
before the first turn is unverified (no gate depends on it).

### Phase 12 implementation record (2026-10-07)

Code (`fb11df79`): 1(a) kept flags after a leading subcommand; 1(b) a resume
tied to a known session dedupes on it; 1(c) a session first established by a
state report is resolved once; 1(d) the pi asset reports `resume_argv` from
`process.argv` (allowlist `--model`/`--thinking`/`--provider`/`--approve`).
Owner additions the same day: the agents area shows the logged-in account
(`ui.show_agent_account`): Claude from `<CLAUDE_CONFIG_DIR or ~>/.claude.json`,
codex from the `id_token` email in `<CODEX_HOME or ~/.codex>/auth.json`, both
polled every 5 s by mtime so a live login change updates the label; pi reports
`pi · <email or provider>` itself through `getApiKeyForProvider`, so
account-switching pi extensions are honored. pi side documented in
`~/.pi/agent/docs/herdr.md`. Tooling and harnesses live in `fork/`.

**Gate results**
- [x] G12.1 unit: placement (claude/codex/pi), session dedupe for two
      variants, account sources/readers/labels; bun suite 28/28 incl. pi
      resume_argv and account switching. Once-per-session state-report
      resolution is covered by code review and the stub e2e, not a unit test.
- [x] G12.2 + accounts: `fork/tests/e2e_deploy.py` scenario A, 20 checks
      (labels follow login changes for claude, codex, pi; exact restore argv
      after restart for all three).
- [x] G12.3 + Phase 11 G2/G3: scenarios B and C, 21 checks (deploy from the
      operator's env with an injected codex install failure, every pane
      verified, clean server env; rollback; injected apply failure rolls back
      without leaving the lock; live herdr unchanged). 41/41 total.
- [x] G12.4: `fork/tests/e2e_claude_angles.py` 5/6 automatic; the picker
      check matched the wrong text (Claude hides `-p` sessions), the screen
      showed the `claude-kee` session listed in `claude-me`'s picker; the
      assertion is fixed.
- [ ] G1 dry-run on the live roots; G4/G12.5 after the live deploy.
- Incident during G12.2 (first attempt): the owner's fish_user_paths put the
  real `claude` and `pi` ahead of the stand-ins inside the isolated root; they
  started with empty isolated config dirs (no credentials, no model call) and
  were killed. The harness now prepends the stand-ins and aborts unless fish
  resolves all three to them.

### Phase 13 - Deploy readiness review [UNHARDENED]

**Claim under review**: Phases 10-12 as BUILT (`fb11df79` code, `3f348547`
tooling) are ready for the live deploy, and the tests listed in the Phase 12
implementation record cover what the live deploy depends on.

**Built artifacts**: `src/agent_resume.rs`, `src/agent_account.rs`,
`src/app/api/panes.rs` (resolver, account watch, once-per-session),
`src/app/api.rs` (detection hook), `src/persist/restore.rs` (session dedupe),
`src/server/headless.rs` + `src/app/runtime.rs` (account poll deadline),
`src/integration/assets/pi/herdr-agent-state.ts`, `herdr.config.toml`,
`fork/deploy/*`, `fork/tests/*`, `~/.pi/agent/docs/herdr.md`.

**Claimed coverage**: see "Phase 12 implementation record". G1 dry-run on the
live roots passed (15 Claude panes + 1 codex captured, nothing stopped).

**Known untested (claimed acceptable)**: real codex and real pi end to end
(credential risk, D1); macOS; `herdr --remote`; the live deploy itself (G4,
G12.5); account polling cost with many panes (5 s, one stat per watched file).

**Decision asked of the review**: which untested angle, if any, must be
tested before the live deploy, and how, at low token cost.

## 5. Decisions log / open questions

- Mode name: `Control` (alternatives considered: `Manage`, `Tab` (too narrow),
  `Command` (collides with prefix-as-command-mode naming in code comments)).
- One mode, not three [SUPERSEDED by Phase 6]: the owner wanted domain-named modes,
  so Phase 6 ships three user-facing modes (TABS/SPACES/AGENTS). The mechanism half
  of this entry survives: internally it is still one `Mode::Control` variant with a
  scope, because multiple top-level mode keys remain unnecessary - entry bindings
  are ordinary actions, not prefixes. Pane verbs stay on prefix bindings and resize mode.
- Reorder wrap-around: no wrap (matches drag semantics and zellij MoveTab).
- Prefix key inside control mode: exits into prefix mode (chaining), a documented
  divergence from resize mode's inert-prefix behavior; considered keeping template
  parity, but a dead key inside a sticky mode serves nobody and the chain is real
  muscle memory (`ctrl+t` browse tabs, `ctrl+b c` create).
- Stickiness mechanism: predicate table + restore-if-Terminal after dispatch, NOT a
  context-aware rewrite of the nav arms; smaller diff, matches the
  `copy_mode_survives_prefix_action` idiom, and modal transitions stay untouched.
- Panes scope (Phase 7, planned): auto-directional split on `n` chosen over a fixed
  split-right (zellij NewPane muscle memory; fixed-right kept as the fallback if the
  rect heuristic feels wrong in manual testing). `1..9` deliberately inert - indexed
  pane focus without visible pane ordinals is a misfire generator; pane index badges
  during Panes scope are the real fix and a separate future item. Arrows stay on the
  global tabs/spaces contract even in Panes scope. 2D swap beyond `i/o`
  (`control_swap_*` fields defaulting to shift+hjkl) considered and deferred: four
  more fields buy a verb the prefix layer already covers (`prefix+shift+hjkl`);
  nothing in the registry prevents adding them later - reservation only applies to
  handler-hardwired keys, configurable fields go through ordinary first-wins
  conflict diagnostics. Upstream entry default `prefix+f` because p/shift+p are taken; personal
  `ctrl+p` restores zellij's own pane-mode key.
- Indexed `1..9` inside the modes: dispatches within the ACTIVE scope (tabs ->
  SwitchTab, spaces -> SwitchWorkspace, agents -> FocusAgent), reserved and
  hardwired. [Superseded the single-mode-era "tabs only" wording in the round-3
  audit; the scoped behavior is what Phase 6 shipped, documented, and tests.]
- Phase 8 build script: brew `zig@0.15` over the official tarball on macOS
  (tarball cannot link on Xcode 26.4+ SDKs; brew backports the fix; dated
  deprecate/disable 2027/2028). `~/.local/share/herdr` as the toolchain home
  (zig tarball, patched lib copy, wrapper) - proceeding under PROPOSAL, owner
  may override (intent record, open item). PATH edits do not pick a shell:
  fish gets `fish_user_paths` whenever its config dir exists AND the `$SHELL`
  rc is edited too (the passwd `$SHELL` misdetects the owner's own Mac; a fish
  config dir survives one `fish -c`) - over-adding is cheap, a missing entry is
  the failure.
  Smoke-test before install, atomic replace - the "never break my installed
  herdr" ruling. The zig tarball is fetched WITHOUT a checksum (TLS plus
  xz/tar integrity; the official installer does verify its binary) - a decision,
  not an oversight. Alpine/musl and Windows are non-goals.
- Open: whether upstream wants `control_*` flat keys or a `[keys.control]` table.
  Flat matches `navigate_*` precedent; a table reads better but changes the
  config-reference model walk. Decide at Discussion time; local build ships flat.
