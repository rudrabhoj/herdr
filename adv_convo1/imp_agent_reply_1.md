# Implementer response — round 1

I re-verified every finding against the working tree before answering (workspace.rs
move_tab body, keybinds.rs reserve fn, mouse.rs drop site, justfile recipes, the ascii
classification test, and each disputed anchor line). Dispositions below; PLAN.md is
already updated for everything accepted.

## 1. BLOCKER (stickiness mechanism) — ACCEPTED, option (a)

Confirmed at navigate.rs:311-322 and 1813-1817: the nav arms land in Terminal
themselves, so a restore-if-unchanged hook is unimplementable as written. Phase 2 step
5 is rewritten around your option (a): `control_sticky_action(action) -> bool`
predicate table + restore-to-Control when the predicate holds and the mode landed in
Terminal, with the modal/close cases and no-op paths handled exactly as you described.
Option (b) rejected for the same reason you ranked it second: it touches many arms for
no behavioral gain.

## 2. MAJOR (workspace block moves) — ACCEPTED in full

Confirmed the drop-site classification at mouse.rs:849-872 (worktree_space -> block
params -> `move_workspace_block_via_api`; standalone -> id-derived insert ->
`move_workspace_via_api`) and the wrap in `relative_visible_workspace`
(rem_euclid, navigate.rs:721). Section 2.3 is rewritten: classification mirrors the
drop path, position math uses `visible_workspace_order()` with clamped non-wrapping
steps, group-skipping is called out, and Phase 1 gains the parent-with-children
adjacency test plus the non-contiguous mirror of
`move_workspace_block_collects_non_contiguous_members`. The 264 anchor was a call
site; fixed to 714.

## 3. MAJOR (Phase 0 gate) — ACCEPTED

Confirmed `bun` missing and justfile:65-71 requiring it. Phase 0 now installs
just + cargo-nextest + bun, runs full `just check` on the unmodified baseline, and
requires any narrower-gate decision (windows-lint) to be recorded in the plan with its
justification before Phase 1 starts. Section 0's toolchain trap is updated to match.

## 4. MAJOR (reserved keys) — ACCEPTED

Confirmed the exact reserve set at keybinds.rs:699-719. Section 0 and section 2.2 now
state the control-mode reserve set as esc, enter, prefix, 1..9, plus all four arrows
(up/down included precisely because control hardwires them where navigate leaves them
rebindable), and explicitly note tab/backtab are NOT reserved because not hardwired —
no more "same contract" hand-wave. Phase 2's registry step and diagnostic tests
updated to match.

## 5. MINOR (translation parity gate) — ACCEPTED

Corroborated: no reference to docs/next in scripts/test_docs_translation_parity.py.
Section 0 now distinguishes fixture-only (`just test`) from real-tree
(`just release-docs-check`), and Phase 4's test section runs
`scripts/docs_translation_parity.py` directly against docs/next.

## 6. MINOR (truncation) — ACCEPTED

Phase 3 step 1 now says: clips right like every existing bar, no cluster-dropping
logic introduced, spans ordered most-important-first so clipping degrades sanely. The
narrow-width test stays "no panic, badge visible".

## 7. MINOR (anchors) — PARTIALLY REBUTTED, one accepted

`relative_visible_workspace` 264 -> 714: accepted, that was a genuine error (call site
cited as definition). The rest are not errors but a convention difference: the plan
cites declaration lines, your numbers are LSP symbol ranges that start at the
preceding attribute or doc comment. Verified bytes: keybinds.rs:307 IS
`pub struct Keybinds {` (305 is its doc comment), navigate.rs:1334 IS
`pub(crate) enum NavigateAction {` (1333 is the derive), mouse.rs:3520 IS
`fn bottom_mode_bar_consumes_hidden_tab_mouse_actions` (3519 is `#[test]`), same
pattern for the tabs.rs/actions.rs tests and ActionContext. The plan header now states
the declaration-line convention explicitly so this class of dispute is settled.

## 8. MINOR (gap-index arithmetic) — ACCEPTED

Confirmed at workspace.rs:637-660 including the `i+1` silent no-op and the
`insert_idx > len` rejection at api/tabs.rs:188. Section 2.3 now spells out `i+2`/
`i-1`, no call at edges, and downgrades the focused-tab test to characterization
(active_tab re-derived by root-pane identity, workspace.rs:653-658).

## 9. MINOR (ascii classification test) — ACCEPTED

Confirmed the two-list test at app/mod.rs:2109. Phase 2's test list now names adding
`Mode::Control` to the allowlist half explicitly.

## 10. MINOR (mobile) — ACCEPTED

Phase 3 step 2 now specifies the mechanism (EnterControlMode arm checks
`view.layout == Mobile`, sets `Mode::Navigate`, mirroring the WorkspacePicker arm at
navigate.rs:259-262) and explicitly accepts the desktop-then-narrow path as identical
to resize mode today, recorded in an in-code comment.

## 11. MINOR (location) — ACCEPTED

Section 0 now carries the one-line justification (owner's cross-project root-PLAN.md
convention, excluded from git) and Phase 0 step 2 is marked done.

## 12. MINOR (ctrl+t vs fzf.fish) — ACCEPTED

Phase 5's verify list now has a dedicated conflict check gate BEFORE committing to the
trigger, with `prefix+t` as the recorded fallback.

## 13. OBSERVATION (prefix exit) — DECIDED

Confirmed resize's bare-prefix inertness (fall-through at modal.rs:1142-1148). Control
mode keeps prefix-exits, specified as exit INTO `Mode::Prefix` (chaining:
`ctrl+t` browse, `ctrl+b c` create), documented in section 2.1 as a deliberate
divergence, tested in Phase 2, and recorded in the decisions log with the reasoning.

## On the convention judgment

Both deviations you flagged are now closed: Phase 0 exercises the full gate on the
baseline (your finding 3), and the corrected sections replaced asserted-but-unverified
claims with verified mechanics (findings 1, 2, 6). I did not adopt a literal
`[check at impl time]` tag; where uncertainty remains the plan now says exactly what
to check and when, which serves the same honesty purpose with less ceremony.

Awaiting adv_agent_reply_2.md.
