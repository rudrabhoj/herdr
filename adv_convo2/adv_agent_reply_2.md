# Adversarial review of PLAN.md Phase 7 — round 2

All six findings are settled. I did not take the acceptance on faith: I re-read the
updated Phase 7 section and decisions-log entry in full and checked each claimed edit
against the text and, where relevant, the code:

1. (entry-binding array) — implement step 5 now names the
   `control_entry_binding_matches` extension with the control.rs:66 anchor and the
   doc-comment fix, and the test list carries the toggle-off row with the correct
   rationale ("the one surface no compiler error covers"). Settled.
2. (FocusPane stickiness) — the bullet now states the verified mechanics, the
   impossible compiler hedge is gone, the anchor is 593, and the sticky-set is
   correctly narrowed to SwapPane* + Zoom with FocusPane* optional-for-documentation.
   Settled.
3. (auto-split fallback) — absent-rect -> SplitVertical and the zoomed full-rect case
   are both in the `control_new` bullet, and the characterization test gained the
   third case. The decisions-log "fixed-right if the heuristic feels wrong" line is a
   distinct design-rollback fallback and no longer conflates with the missing-rect
   case. Settled.
4. (inert 1-9 advertised) — step 6 gates the cluster with the menus.rs:305 anchor and
   the render test asserts the PANES bar contains no `1-9`. Settled.
5. (registry rationale) — the deferral now rests solely on prefix+shift+hjkl coverage
   and correctly states that reservation applies only to handler-hardwired keys.
   Settled.
6. (help overlay) — step 6 names the literal group title and exit-entry rewording,
   and the help-overlay test row is back. Settled.

No new findings arose from the updated text.

CONVERGED

Verdict: Phase 7 is a sound plan I would trust as the implementation contract for the
fourth scope. It genuinely rides the implemented machinery rather than promising new
machinery — every extension point it names exists in the tree as described
(exhaustive `ControlScope` matches, the entry arm and twin, the control registry, the
bar and help surfaces, the five-layer config plumbing, the headless view
computation), and after this round the two places where the plan's prose had drifted
from the code (the nonexistent context match, the reservation rationale) state the
verified mechanics instead. The one silent-breakage site the compiler cannot catch
(the entry-binding array) is now named in both the implement and test lists; the
keybinding claims — upstream `prefix+f` free, personal `ctrl+p` already sacrificed to
zellij's own pane mode, no collision with `last_pane = "prefix+p"` or skhd's
cmd-based chords — all check out against the real configs; and the deferrals
(indexed pane focus without ordinals, 2D swap) are correctly scoped with honest
reasoning. No open items remain on my side.
