# Adversarial review of PLAN.md — round 3

CONVERGED

Verdict: the plan is now sound and I would trust it as the implementation contract.
Every load-bearing claim was verified against the tree at `10974c82` — mode dispatch
(both the monolithic and headless key routers), the resize-mode template, the action
arms and their mode mutations, the keybind registry and reserved-key machinery, the
remote overlay, the mouse drag/drop paths including the worktree block-move
classification, the UI bar and mouse-guard layers, the API handlers, the justfile
gates, the maintenance scripts, and the cited GitHub issues. The one blocker (a
stickiness mechanism that could not work against the real `finish_action_context`
semantics) was replaced with a predicate-table design I verified holds for every
action in the control keymap, including the create/close edge cases; the three majors
(worktree block moves, the untested phase gate and missing bun, the reserved-key
contract) are fixed with mechanics that match the code; all minors and both round-2
editorial residuals are confirmed landed in the file, and the plan now honors the
owner's convention at least as faithfully as the covalent reference — traps-first,
declaration-line anchors stated as a convention, phases with independently executable
Goal/Implement/Test/Verify gates, and the right kinds of tests (pure-state, config
diagnostics, buffer-row renders, adversarial invariants, per-phase manual matrices)
for what each phase touches. No open items remain on my side.
