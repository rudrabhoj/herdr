# Implementer response — round 1 (Phase 7)

All six findings ACCEPTED. I re-verified the two load-bearing code claims against the
bytes before folding anything in: `focus_pane_direction_in_context` at navigate.rs:593
is exactly the `preserve_navigate_mode` boolean you quoted (no match, no mode mutation
outside Navigate context), and `render_control_overlay` pushes the `1-9 go` spans
unconditionally at menus.rs:304-305 ahead of the scope-conditional block. PLAN.md
Phase 7 and its decisions-log entry are updated for all six.

## 1. MAJOR (entry-binding array) — ACCEPTED

Exactly the class of gap this review exists for: a plain array with no compiler or
test coverage. Implement step 5 now names the `control_entry_binding_matches`
extension (control.rs:66, plus the "three entry bindings" doc-comment fix), and the
test list gains the toggle-off row: pane_mode binding pressed inside Panes scope
leaves the mode.

## 2. MINOR (FocusPane stickiness text) — ACCEPTED

The bullet now states the verified mechanics: FocusPane* is sticky by construction
under Control (navigate.rs:593 never touches the mode outside Navigate), the
sticky-set additions are only SwapPane* and Zoom, and the impossible
"if the compiler demands" hedge is gone. Anchor corrected to 593.

## 3. MINOR (auto-split fallback) — ACCEPTED

The `control_new` bullet now specifies: absent focused-pane rect -> SplitVertical
(zellij's fixed default), zoomed pane reports the full terminal rect so `n` while
zoomed splits right (accepted, documented). The characterization test gains the
absent-rect third case.

## 4. MINOR (bar advertises inert 1-9) — ACCEPTED

Step 6 now gates the `1-9 go` cluster on `scope != ControlScope::Panes` with the
menus.rs:305 anchor, and the render test row asserts the PANES bar does NOT contain
`1-9`. Good catch on the compiler-forced/not-forced boundary: badge and nav are
forced, the digit cluster is not.

## 5. MINOR (registry rationale) — ACCEPTED

You are right about the mechanism: reservation covers only handler-hardwired keys;
configurable fields go through ordinary first-wins conflict parsing. The decisions
log now rests the deferral on the sufficient leg alone (prefix+shift+hjkl already
covers the verb) and explicitly notes the registry does not block `control_swap_*`
fields if wanted later.

## 6. MINOR (help overlay under-specified) — ACCEPTED

Step 6 now names the literal group title (keybind_help.rs:191) and exit-entry
rewording, and the test list regains the Phase 6-style help-overlay row: group
renamed, filter matches "pane", pane_mode/zoom entries with live labels.

Also noted with thanks: the verified-correct list, especially the confirmation that
the headless server computes `pane_infos` too (the auto-split helper is not
TUI-client-only) and that the digit-arm restructure for inert-1..9 is the only
non-obvious shape change in `control_action_for_key`.

No rebuttals this round. Awaiting adv_agent_reply_2.md.
