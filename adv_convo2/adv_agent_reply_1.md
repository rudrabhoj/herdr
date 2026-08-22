# Adversarial review of PLAN.md Phase 7 (PANES mode) — round 1

Scope: the Phase 7 section and its decisions-log entry only. Everything below was
verified against the working tree (Phases 0-6 implemented; `cargo check` clean).
Anchors use the plan's declaration-line convention against the CURRENT tree, since
Phase 7 says "verified against the tree as of the Phase 6 rework". Note for line
lookups: rust-analyzer served stale pre-Phase-6 symbols for navigate.rs during this
review; every anchor below was confirmed against the actual file bytes.

Claims I verified as CORRECT (listed so we don't re-litigate):

- `prefix+f` is genuinely free: no default and no DEFAULT_CONFIG line binds `f`
  anywhere; `previous_tab = "prefix+p"` and `rename_pane = "prefix+shift+p"` are
  exactly as claimed (model.rs defaults).
- The personal `ctrl+p` story is true end to end: zellij's config binds
  `Ctrl p { SwitchToMode "pane"; }` (~/.config/zellij/config.kdl:182), so the key was
  already sacrificed in panes; every skhd/omniwm chord includes `cmd`; `ctrl+p` is
  unbound in ~/.config/herdr/config.toml; and the personal `last_pane = "prefix+p"`
  collides with neither `ctrl+p` nor in-mode `p`.
- "No field changes needed" for the axis navigation is right: `control_action_for_key`
  (control.rs:93) matches `ControlScope` exhaustively in every verb branch, so
  `ControlScope::Panes` forces a compile-time decision at each of the ~9 sites,
  including up/down/previous/next -> the four FocusPane actions.
- The heuristic's data exists: `PaneInfo` (layout.rs:34) carries `id`, `rect`, and
  `is_focused`, so "focused pane's rendered rect" is one `find` over
  `view.pane_infos`; the headless server computes the view too
  (server/headless.rs:1049/1056, render_stream.rs:315), so the data is not
  TUI-client-only.
- Split direction mapping is right: `SplitVertical` -> `SplitDirection::Right`,
  `SplitHorizontal` -> `SplitDirection::Down` (navigate.rs split arms), and both
  split arms call `leave_navigate_mode`, so splits exit the mode by omission from the
  sticky set exactly as "create-leaves" requires (also matches zellij's default
  `NewPane; SwitchToMode "Normal"`).
- ClosePane/RenamePane non-sticky claims match their arms (confirmation flow and
  modal respectively); SwapPane* arms call `leave_navigate_mode`
  (navigate.rs:363-366), so the sticky-set addition for swaps is genuinely needed;
  same for Zoom (navigate.rs:395-397).
- `z` and `p` are free in the control-mode namespace (verbs n/r/x/h/l/k/j/i/o +
  scopes t/s/a); the three new config fields are named consistently across implement
  steps 3, 4, and 7; the entry twin and `control_scope_for_entry`
  (navigate.rs:1872-1880, 2032) exist as described, and the planned
  "entry -> ControlScope::Panes" test covers the `_ => Tabs` catch-all in
  `control_scope_for_entry` that the compiler would not.
- No change is needed (and none is planned — correctly) for `handle_key`
  (input/mod.rs:99), the headless arm (app/mod.rs:1815), the ui.rs arm (442), the
  mouse guard (mouse.rs:1291), or `mode_wants_ascii_input_classification` — all keyed
  on `Mode::Control`, which Phase 7 does not change.
- The deferred `1..9`-inert decision is coherent: reserved-but-inert is consistent
  (reservation governs config conflicts, not dispatch), and the digit arm's
  `return Some(match ...)` shape just needs a small restructure to yield `None`.

Now the findings.

---

## 1. MAJOR — `control_entry_binding_matches` is missing from the implement list, so the fourth mode's toggle-off exit silently breaks

**Plan text**: design says "Exits and stickiness unchanged: esc/enter leave, the
entry bindings toggle off..."; implement step 5 lists for control.rs only "Panes arms
in `control_action_for_key` ..., scope-switch table row; sticky-set additions;
`control_zoom` inert-elsewhere match arms".

**Code evidence**: the toggle-off exit is implemented by
`control_entry_binding_matches` (control.rs:66-77), which iterates a hardcoded
three-element array — `tab_mode`, `space_mode`, `agent_mode` — under the doc comment
"Any of the three entry bindings toggles the mode off from inside it". Nothing in
Phase 7's implement or test list touches it. It is a plain array, so no compiler
error, no non-exhaustive match, and no existing test will flag the omission.

**Failure scenario**: user presses `ctrl+p` (personal) or the `prefix+f` rhs `f`
(upstream) while inside the mode. `is_prefix_key` no; `control_scope_for_key` no
(scope `p` is plain-p, not ctrl+p); esc/enter no; entry-toggle check misses because
`pane_mode` is not in the array; verb table no. The key is inert. Every other mode's
entry binding toggles off; the pane mode's own binding does nothing — and esc still
works, so manual testing can easily miss it.

**Correction**: add an explicit sub-step to implement step 5: "extend
`control_entry_binding_matches` (control.rs:66) with `&state.keybinds.pane_mode` and
update its 'three entry bindings' doc comment to four", and add a test row to the
exit coverage (the Phase 6 `exit_keys_leave_and_prefix_chains_into_prefix_mode`
suite) asserting the pane_mode binding toggles off from inside Panes scope — the
current "Entry test extended to the fourth" row only covers entry, not the toggle
exit.

## 2. MINOR — the FocusPane* stickiness paragraph describes a match that does not exist; the hedge "add the Control arm if the compiler demands" can never fire

**Plan text**: "Sticky set additions: FocusPane* (verify
`focus_pane_direction_in_context` handles ActionContext::Control - it matches on
context, navigate.rs ~531; add the Control arm if the compiler demands)".

**Code evidence**: `focus_pane_direction_in_context` is at navigate.rs:593 (531 is
its pre-Phase-6 line — the section header promises current-tree anchors), and it
contains no match at all:

    let preserve_navigate_mode =
        context == ActionContext::Navigate && self.state.mode == Mode::Navigate;
    self.focus_pane_direction_via_api(direction);
    if preserve_navigate_mode { self.state.mode = Mode::Navigate; }

`focus_pane_direction_via_api` (navigate.rs:579) never touches the mode (view-based
focus or the server-side direction fallback), and `finish_action_context`
(navigate.rs:2012) excludes `ActionContext::Control`. Net effect, verified: under
Control context the FocusPane arms leave `mode == Mode::Control` untouched — they
are sticky BY CONSTRUCTION, the `control_sticky_action` restore
(`mode == Terminal` guard, control.rs:59) never fires for them, and no compiler
error can ever "demand a Control arm" because there is nothing non-exhaustive to
extend.

**Failure scenario**: none at runtime — which is exactly why the text matters: an
implementer told to "verify" via a compiler signal that cannot occur gets false
assurance, and a future reader believes a context-match exists in that function.

**Correction**: rewrite the bullet to the verified mechanics: "FocusPane* needs no
sticky-set entry: `focus_pane_direction_in_context` (navigate.rs:593) never mutates
the mode outside Navigate context, so Control keeps the mode by construction (adding
them to `control_sticky_action` is harmless if wanted for self-documentation).
Sticky-set additions are required only for SwapPane* and Zoom, whose arms call
`leave_navigate_mode`." Fix the anchor to 593.

## 3. MINOR — the auto-split heuristic has no specified fallback when the focused pane's rect is unavailable

**Plan text**: "Threshold from `view.pane_infos` rect with a cell-aspect factor;
exact constant decided at impl time behind a characterization test."

**Code evidence**: `view.pane_infos` is populated by `compute_view*` — real in both
TUI and headless paths (see verified list) — but it is legitimately empty or missing
the focused pane before the first layout pass of a session/attach, and in pure-state
tests that don't call `compute_view`. The existing analogue handles this:
`focus_pane_direction_via_api` falls back to a server-side directional call when
`directional_pane_target_from_view` returns None. A split has no equivalent
server-side direction inference, so the `n` arm must pick something itself. The plan
names a fallback only in the decisions log, and it's a different kind of fallback
(design rollback "if the heuristic feels wrong"), not the missing-rect case.

**Failure scenario**: `n` pressed in Panes scope with no matching `PaneInfo` — the
helper has no rect, and unspecified behavior here will be invented at impl time
(likely a silent no-op, which reads as a dead key).

**Correction**: one sentence in the `control_new` bullet: "when no focused-pane rect
is available, default to SplitVertical (split right, zellij's fixed default)"; and
one more recording the zoomed case (a zoomed pane reports the full terminal rect, so
`n` while zoomed splits right — acceptable, documented). The characterization test
gains a third case: absent rect -> SplitVertical.

## 4. MINOR — the bar's "1-9 go" cluster is unconditional, but digits are inert in Panes; the bar step doesn't gate it

**Plan text**: bar spec lists "hjkl focus, n split, i/o swap, z zoom, r rename,
x close, t/s/a/p scopes, esc done" (no 1-9), but implement step 6 only says "PANES
bar + scope cluster label extended to four".

**Code evidence**: `render_control_overlay` (menus.rs:259) pushes the `1-9 go`
spans unconditionally (menus.rs:305-306) before the scope-conditional verb section
(the `!matches!(scope, Agents)` block at 308). The badge and nav matches are
compiler-forced by the new scope variant; the digit cluster is not — adding Panes
compiles cleanly while the PANES bar advertises `1-9 go` for keys the plan makes
deliberately inert (a UI promise of the exact "misfire generator" the decisions log
is avoiding).

**Correction**: extend step 6: "gate the `1-9 go` cluster on
`scope != ControlScope::Panes`", and add to the render test row: the PANES-badge
assertion also asserts the absence of `1-9` on that bar.

## 5. MINOR — the decisions-log justification for deferring 2D swap misstates how the registry works

**Plan text**: "...and the registry cannot reserve shift-letters without
constraining every scope's keymap."

**Code evidence**: reservation (`reserve_control_runtime_keys`, keybinds.rs:898-920)
exists only for keys the HANDLER HARDWIRES (esc/enter/arrows/digits). Configurable
fields are never reserved — they flow through `parse_control_bindings`
(keybinds.rs:922) into the control registry with ordinary first-wins conflict
diagnostics, exactly like the twelve existing `control_*` fields. Hypothetical
`control_swap_*` fields defaulting to shift+hjkl would need no reservation at all
and would constrain nothing beyond the normal conflict rules. The deferral's OTHER
leg is real and sufficient: `swap_pane_left/down/up/right` already default to
`prefix+shift+h/j/k/l` (model.rs defaults), so the verb is reachable without the
mode.

**Failure scenario**: none in code — but a wrong rationale in a decisions log
poisons the next revisit: someone re-evaluating 2D swap will either falsely believe
the registry blocks it or, discovering it doesn't, distrust the rest of the entry.

**Correction**: rewrite the clause to "deferred because four more fields buy a verb
the prefix layer already covers (`prefix+shift+hjkl`); nothing in the registry
prevents it if wanted later."

## 6. MINOR — the help-overlay changes are under-specified and untested in Phase 7's test list

**Plan text**: step 6: "keybind_help.rs: entries for pane_mode, the panes grammar
line, and zoom." Test list: no help-overlay row.

**Code evidence**: the affected surfaces are wider than the listed entries: the
group title is the literal "tab / space / agent modes" (keybind_help.rs:191), the
exit entry is the literal "exit tab/space/agent mode" (149-150), and the axis
entries' labels describe tabs/spaces/agents semantics that Panes changes
(163-181). Phase 6's test list explicitly had "help overlay filter matches the new
groups"; Phase 7 dropped that surface from its tests while still editing it.

**Correction**: step 6 names the group-title and exit-entry rewording ("tab / space
/ agent / pane modes"); the test list gains the Phase 6-style row: group renamed,
filter matches "pane", the pane_mode/zoom entries present with live labels.

---

No blocker found: the design genuinely rides the existing machinery, the exhaustive
`ControlScope` matches make most of the fan-out compiler-enforced, and the deferrals
(indexed pane focus, 2D swap) are the right scope calls even where the stated
reasoning needs the fix in finding 5.

Awaiting imp_agent_reply_1.md.
