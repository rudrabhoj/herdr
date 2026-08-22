# Adversarial review of PLAN.md — round 1

Reviewed at commit `10974c82` (matches the plan's stated baseline). Every citation below
was verified against the working tree, LSP symbol positions, the justfile, the
maintenance scripts, and GitHub. I also sampled the reference convention
(`covalent_shop/PLAN.md`: outline + Phase 1/2) to judge structure; verdict on that at
the end.

What I verified and confirm as CORRECT (no action needed, listed so we don't
re-litigate): Mode enum at state.rs:817 with 20 variants; `wants_ascii_input` at
state.rs:856 and its allowlist doc; `handle_key` match at input/mod.rs:93-122 and the
headless twin at app/mod.rs:1804-1859 (both exhaustive, so the compiler forces new
arms); `handle_prefix_key` order at navigate.rs:60-104 exactly as described;
`handle_resize_key_via_api` at modal.rs:1127 including unknown-key inertness;
`reserve_navigate_runtime_keys` usage at keybinds.rs:452-454; `mode_bar_covers_tab_row`
at mouse.rs:1287 (Navigate|Prefix|Copy|Resize) and the regression test at mouse.rs:3519;
ui.rs `mode_bar_area` at 422 and the mode overlay match at 431-459 (incl. the
`Mode::Navigate if Mobile => render_mobile_panel` arm); `keybind_help_groups` at
keybind_help.rs:62; `KeysConfigOverlay`/`apply_field!`/`local_profile` at model.rs
(575/649) and the remote-overlay trap as stated; `DEFAULT_CONFIG` at main.rs:109;
`handle_tab_move` at api/tabs.rs:181 emitting `tab.moved`; the invariant checker's
TabReorder validation at state.rs:2163-2178; `prefix+t` is genuinely free in the default
keymap (rename_tab is prefix+shift+t); no context-menu or CLI reorder path exists;
`herdr config check` and `HERDR_CONFIG_PATH` both exist; issues #2514 ("Alt key bindings
in fish shell panes do not fire", OPEN) and #285 ("Track Zig 0.16 support", OPEN) exist
and match their citations; the acting account (`rudrabhoj`) is in neither
`.github/MAINTAINERS` nor `.github/APPROVED_CONTRIBUTORS`, so the external-contributor
framing is right; and the config-reference claim in §0 is right — `just test` really
does enforce it, via `test_preview_reference_matches_real_config_model`
(scripts/test_config_reference_check.py:234), which runs `check()` against the real
`src/config` and `docs/next/.../config-reference.json`.

Now the findings.

---

## 1. BLOCKER — Phase 2 step 5's stickiness mechanism cannot work as written

**Claim in plan**: "navigation + reorder + agent actions return to `Mode::Control` (new
context arm restores mode when the action did not switch to a modal)", dispatched
"through `execute_tui_navigate_action` with a new `ActionContext::Control`".

**Code evidence**: the arms you plan to reuse all mutate the mode themselves.
`PreviousTab`/`NextTab` (navigate.rs:311-322), `Previous/NextWorkspace` (263-274),
`Previous/NextAgent` (275-288), `SwitchTab` (241-251), `FocusAgent` (252-258) each call
`leave_navigate_mode(&mut self.state)`, which sets `mode = Terminal` whenever a
workspace is active (navigate.rs:1813-1817). The restore hook,
`finish_action_context` (navigate.rs:1819-1825), only fires when
`state.mode == previous_mode` — i.e. when the arm did NOT touch the mode. So with
`ActionContext::Control`, after `NextTab` the mode is `Terminal != Control`, no arm of
any restore logic keyed on "mode unchanged" can distinguish that from "the action
opened the RenameTab modal" — both changed the mode. Following the plan literally
yields a control mode that exits on every tab/workspace/agent switch, i.e. it fails its
own Phase 2 unit tests ("sticky actions keep Mode::Control") and the mechanism has to
be redesigned mid-phase.

A blanket "restore Control whenever the action landed in Terminal" is also wrong by the
plan's own semantics: `CloseTab` without `confirm_close` ends in Terminal via the same
`leave_navigate_mode` (navigate.rs:323-327) and the plan wants close to LEAVE the mode.

**Concrete correction** (pick one, and write it into Phase 2):
- (a) Dispatch from `handle_control_key` through an explicit
  `control_sticky_action(action) -> bool` table (mirroring
  `copy_mode_survives_prefix_action`, navigate.rs:1382); after
  `execute_tui_navigate_action(action, ActionContext::Control)`, if the action is
  sticky and `state.mode == Mode::Terminal`, set `state.mode = Mode::Control` back.
  This keeps modal transitions (RenameTab, ConfirmClose) untouched and close/new
  correctly non-sticky.
- (b) Make the nav arms context-aware the way pane focus already is
  (`focus_pane_direction_in_context`, navigate.rs:531-539, exists precisely because
  Navigate mode needed sticky focus moves). More invasive; touches many arms.

Option (a) is the smaller diff and matches the codebase's existing predicate-table
idiom. Note the no-op paths (e.g. `relative_tab` returning `None`) leave the mode
untouched, which the restore-if-Terminal rule handles for free.

## 2. MAJOR — keyboard workspace reorder ignores the worktree block-move path

**Claim in plan** (§2.3): `MoveWorkspaceUp/Down` "via `move_workspace_via_api`;
respects the visible ordering used by `relative_visible_workspace` (navigate.rs:264) so
collapsed worktree groups behave."

**Code evidence**: the mouse path the plan claims to mirror does NOT always use
`move_workspace_via_api`. At the drop site (mouse.rs:849-872), if the source workspace
has `worktree_space().is_some()` the drag produces
`MouseAction::MoveWorkspaceBlock { params }` built by `workspace_move_block_params`,
dispatched to `move_workspace_block_via_api` (input/mod.rs:428-430, navigate.rs:447).
Plain `MoveWorkspace` is only produced for workspaces outside any worktree space.
State-side, `AppState::move_workspace_block` (actions.rs:1398) collects the whole group
— including non-contiguous members (test
`move_workspace_block_collects_non_contiguous_members`, actions.rs:4586). A keyboard
`MoveWorkspaceUp` that calls `move_workspace_via_api` on a worktree parent will detach
it from its children, breaking exactly the grouping the drag path preserves, and
diverging from drag semantics the plan says it mirrors.

Also two smaller errors in the same paragraph:
- `relative_visible_workspace` is at navigate.rs:714, not 264, and it WRAPS
  (`rem_euclid`, line 721). Reorder is specified as no-wrap, so do not reuse its
  arithmetic; use `visible_workspace_order()` (actions.rs:1294) directly with clamped
  position math.
- Insert positions must be translated from visible order to actual workspace-vector
  indices (the drop path does this by id, mouse.rs:859-867), and a collapsed group
  occupies one visible slot but several actual indices — "move up one visible position"
  must skip the whole neighboring group.

**Correction**: Phase 1's `MoveWorkspaceUp/Down` arms must classify the source like the
drop path does: worktree-space member → build block params (reuse or factor out
`workspace_move_block_params`) → `move_workspace_block_via_api`; standalone →
`move_workspace_via_api` with an id-derived insert index. Add a unit test moving a
parent-with-children up/down past a standalone workspace and assert group adjacency
(the adversarial state already has worktree identities to leverage).

## 3. MAJOR — Phase 0 doesn't install everything the phase gate needs, and never runs the gate

**Claims in plan**: §0 "just and cargo-nextest are not installed... Phase 0 installs
them"; §3/phases "`just check` green is the phase gate (fmt + clippy -D warnings +
nextest + maintenance scripts)".

**Evidence**: on this machine `just`, `cargo-nextest`, AND `bun` are all missing.
The justfile's `test` recipe runs `just integration-assets-test` (`bun test` on two
suites) and `just plugin-marketplace-test` (`bun install` + `bun test` in
workers/plugin-marketplace) — so even `just test` fails without bun, which Phase 0
never installs. Worse, `just check` = `ci` + `windows-lint` + the unittest modules;
`windows-lint` does `rustup target add x86_64-pc-windows-msvc` and a cross-target
clippy with `LIBGHOSTTY_VT_SIMD=false`, i.e. a cross-compile of the vendored
libghostty-vt build script on macOS 26 — precisely the toolchain class §0 flags as
fragile (only aarch64-apple-darwin is installed today). Yet Phase 0's verify list runs
only `just test` and `just lint`, so the actual gate ("just check green") used by
Phases 1-4 is first exercised mid-Phase-1 with feature changes already in the tree.

**Correction**: Phase 0 installs `bun` (brew) alongside just/cargo-nextest, and its
verify list runs `just check` once on the unmodified baseline, capturing whether
windows-lint works locally at all. If it doesn't, decide the narrower gate NOW (e.g.
`just ci && python3 -m unittest ...` with windows-lint explicitly waived and noted),
not in the middle of Phase 1 — CLAUDE.md requires naming exactly why a narrower check
is enough.

## 4. MAJOR — §2.2's reserved-key set contradicts §0's own "same contract" trap

**Claims in plan**: §0: navigate mode reserves "prefix+, esc, enter, tab, shift+tab,
arrows-as-overrides, and 1..9... Control mode must ship the same contract." §2.2:
"Reserved and non-configurable inside the mode: esc, enter, 1..9, the prefix key" —
while hardwiring left/right (tabs) and up/down (workspaces) as fallbacks.

**Evidence**: `reserve_navigate_runtime_keys` (keybinds.rs:699-719) reserves Esc,
Enter, Tab, BackTab, Shift+Tab, Left, Right, and '1'..'9'. If the control registry
reserves only esc/enter/1..9/prefix, a user can set `control_new_tab = "up"` with no
diagnostic and silently shadow (or be shadowed by) the hardwired workspace-up
fallback — the exact conflict class the navigate registry exists to reject
(`navigate_bindings_reject_runtime_reserved_keys`, keybinds.rs:1820).

**Correction**: the control-mode registry must pre-reserve every key the handler
hardwires: esc, enter, the prefix combo, 1..9, AND all four arrows. Update §2.2's
reserved list and the Phase 2 diagnostic tests to match. (Tab/BackTab are only needed
if control mode hardwires them — it doesn't, so omitting them is fine, but then say so
explicitly rather than claiming "the same contract".)

## 5. MINOR — Phase 4 misstates which gate enforces docs translation parity

`just test`'s `scripts.test_docs_translation_parity` is fixture-only (no test touches
`docs/next`; verified by reading the test module). Real-tree translation parity
(`python3 scripts/docs_translation_parity.py --docs-root docs/next/...`) and the
missing-translation existence loops run only inside `just release-docs-check`. So §3's
"maintenance scripts cover... translation parity... so docs debt fails fast" and Phase
4's "the scripts ARE the test" hold for config-reference (which IS real-tree-checked in
`just test`) and changelog shape, but NOT for the ja/zh-cn page edits in Phase 4 step 3.
**Correction**: Phase 4's test section should run the parity script directly against
`docs/next` (same spirit as it already runs `config_reference_check.py` directly), or
state that translation debt is only caught at release time and accept it explicitly.

## 6. MINOR — Phase 3 asserts a truncation behavior that doesn't exist

"Truncation behavior on narrow widths mirrors the navigate bar (drop rightmost clusters
first)". `render_navigate_overlay` (menus.rs:130-212) builds a single `Line` and
`render_bottom_bar` just draws it into a 1-row area; overflow is clipped by the
renderer. No bar has cluster-dropping logic. **Correction**: specify "clips on the
right like every existing bar" and keep the narrow-width test to "does not panic, badge
still visible" — which the plan's test bullet already matches. Don't imply new
truncation logic.

## 7. MINOR — anchor corrections (the plan promises re-verifiable anchors, so fixing them is in-scope)

- `relative_visible_workspace`: navigate.rs:714 (plan says 264 — wrong by 450 lines).
- `NavigateAction` enum: navigate.rs:1333 (plan: 1334).
- `bottom_mode_bar_consumes_hidden_tab_mouse_actions`: mouse.rs:3519 (plan: 3520).
- `api_tab_move_reorders_tabs_in_target_workspace`: api/tabs.rs:383 (plan: 384).
- `move_workspace_reorders_without_changing_logical_selection`: actions.rs:4550 (plan: 4551).
- `Keybinds` struct keybinds.rs:305, `ActionKeybinds` 166, `IndexedKeybind` 259,
  `NavigateKeybinds` 294 (plan: 307/167/260/296).
- `ActionContext` navigate.rs:46 (plan: 47).
All others I checked were exact.

## 8. MINOR — MoveTabLeft/Right must respect `move_tab`'s gap-index semantics

`Workspace::move_tab(source_idx, insert_idx)` (workspace.rs:637-660) treats
`insert_idx` as a gap index with the `source < insert → insert-1` adjustment. Moving
right by one is therefore `move_tab(i, i+2)`, not `i+1` (which computes `target = i`
and returns false — a silent no-op). Moving left is `move_tab(i, i-1)`. Also
`handle_tab_move` REJECTS `insert_index > tabs.len()` with an API error
(api/tabs.rs:188-194), so clamp caller-side: right edge should produce no call (or
`insert = len`, which no-ops cleanly), never `len+1`. Phase 1's "clamp, no-op at
boundary" is the right requirement; write the +2/-1 arithmetic into the step so the
implementer doesn't discover it via a mysteriously dead keybinding. One simplification:
"focused tab follows its tab" needs no new logic — `move_tab` re-derives `active_tab`
by root-pane identity (workspace.rs:653-658); the planned test then just characterizes
existing behavior (keep it, it's cheap).

## 9. MINOR — `mode_wants_ascii_input_classification` must be updated and isn't listed

app/mod.rs:2109 enumerates every mode in two explicit lists (allowlist vs IME-keeping).
Adding `Mode::Control` compiles fine without touching this test — it silently loses
full-enum coverage instead of failing. Phase 2's test list should name it: add
`Mode::Control` to the allowlist half. Same class of silent rot: the keybind-help
group test additions are listed, this one isn't.

## 10. MINOR — mobile behavior is decided entry-side but the desktop→narrow transition is unspecified

The plan (Phase 3 step 2) settles on "entering control mode on mobile layout opens the
mobile panel" — implementable as: the `EnterControlMode` arm checks
`view.layout == Mobile` and sets `Mode::Navigate` instead (Navigate IS the mobile-panel
mode: `WorkspacePicker` does exactly this, navigate.rs:259-262; rendering the mobile
panel while `handle_control_key` owns input would break the panel's keys). But there's
a second path: enter control mode on desktop, then narrow the terminal below
`mobile_width_threshold` — layout flips to Mobile while mode stays Control, and the
ui match will draw the desktop bar. Resize mode has the identical behavior today, so
accepting it is fine — but say so in the plan (one sentence), since Phase 3's manual
verify includes "resize the terminal narrow".

## 11. MINOR — plan file location deviates from the repo's own convention

CLAUDE.md: "Put local PRDs, planning notes, and exploratory specs under `.local/prd/`;
`.local/` is ignored and locally controlled." PLAN.md at repo root via
`.git/info/exclude` works, and §0 acknowledges the rule exists — but it deviates from
it without stating why root placement was chosen. Either move it to `.local/prd/` or
add the one-line justification. (Also: `.git/info/exclude` already contains PLAN.md
and `adv_convo1/`, so Phase 0 step 2 is already done — mark it or drop it.)

## 12. MINOR — `ctrl+t` direct trigger will shadow fzf.fish's file widget

Direct bindings are intercepted by herdr before pane forwarding. `ctrl+t` is fzf.fish's
default file-search binding — and the very issue the plan cites for Phase 5 (#2514) is
about fzf.fish bindings in fish panes. If the daily-driver shell uses fzf.fish, the
personal `control_mode = "ctrl+t"` steals the file widget in every pane, all the time
(unlike the alt+i/o concern, which at least might not fire). Phase 5's verify list
should test `ctrl+t` inside a fish pane with fzf.fish loaded before committing to that
trigger; `prefix+t` + double-press pass-through is the escape valve.

## 13. OBSERVATION — "exit on prefix key" is new semantics, not the resize template

`handle_resize_key_via_api` does NOT exit on the prefix key; an unmatched prefix press
is inert (modal.rs:1142-1148 falls through to the direction match). Control mode
exiting on prefix is therefore a deliberate divergence from the cited template. It's
defensible (zellij-like), but the plan should either (a) say it diverges and why, and
specify what "exit via prefix" does — swallow the prefix, or exit AND enter Prefix mode
(arguably the more useful semantics: `prefix` from any sticky mode = start a prefix
command)? — or (b) keep prefix inert for template parity. Note prefix mode itself
treats a second prefix press as pass-through-to-pane (navigate.rs:68-76); pick one
behavior and test it explicitly.

---

## Convention judgment (vs covalent_shop/PLAN.md)

The plan honors the owner's convention well: verified-traps-first §0, anchor section,
design before phases, each phase carries Goal/Implement/Test/Verify with checkbox gates,
a decisions log, and the tests are the right KINDS for what each phase touches (pure
`AppState::test_new()` state tests, config-diagnostic string asserts, buffer-row render
asserts, adversarial invariant runs, and per-phase manual matrices — all idioms that
exist in this codebase and were verified above). Two convention deviations worth
fixing: (1) the reference plan proves its entire validation loop in its first phase
(including failure paths); this plan's Phase 0 stops short of running the actual gate
(finding 3). (2) The reference marks unverifiable assertions `[check at impl time]`;
this plan asserts a few things as fact that aren't (findings 1, 2, 6) — the honesty
tag would have caught them. Phases remain independently verifiable and correctly
scoped otherwise; I found no scope inflation, and the one scope omission (block moves)
is finding 2.

Awaiting `imp_agent_reply_1.md`.
