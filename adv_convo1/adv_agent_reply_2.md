# Adversarial review of PLAN.md — round 2

I re-read the updated PLAN.md in full and re-verified the disputed points against the
tree before answering.

## Settled

- **Finding 1 (stickiness)** — settled. The rewritten Phase 2 step 5 and the decisions
  log entry are correct as written. I additionally stress-tested the one case the
  mechanism doesn't mention: `NavigateAction::NewWorkspace` on the immediate-create
  path does not rely on any context hook — `begin_tui_workspace_create` sets
  Terminal/Navigate itself (creation.rs:119-123), so omission from the sticky table
  yields the intended "create leaves the mode" behavior, and the prompt path lands in
  the dialog mode. No hole.
- **Finding 2 (block moves)** — settled; §2.3 and Phase 1's new grouping tests are
  accurate against mouse.rs:849-872 and actions.rs:1398/4586. One implementation note,
  not a finding: `workspace_move_block_params(source_ws_idx, drop_target)` takes a
  `WorkspaceDropTarget` (`Before(ws_idx)`/`End`), so the keyboard path will synthesize
  a drop target from the visible-order math; the plan's wording already implies this.
- **Finding 3 (Phase 0 gate)** — settled; Phase 0 now installs bun and baselines
  `just check` with an up-front narrower-gate decision rule.
- **Finding 4 (reserved keys)** — mechanism settled in §0 and Phase 2 step 2, but see
  the residual below: §2.2 was NOT actually updated.
- **Findings 5, 6, 8, 9, 10, 11, 12** — settled; the claimed edits are present and
  match the code (I checked each against the cited lines).
- **Finding 7 (anchors)** — REBUTTAL ACCEPTED, my error on all but the one you
  conceded. I verified the bytes: keybinds.rs:307 is `pub struct Keybinds {` (305/306
  are doc comment + derive), navigate.rs:1334 is the `NavigateAction` declaration
  (1333 is the derive), mouse.rs:3520 is the test fn (3519 is `#[test]`), and the
  declaration-line convention now stated in the plan header settles the class. My
  numbers were LSP symbol-range starts. Withdrawn.
- **Finding 13 (prefix exit)** — settled. Exit-into-`Mode::Prefix` is coherent,
  implementable (both modes are in `wants_ascii_input`, so `sync_prefix_input_source`
  won't flap), documented as a divergence, and tested. Good decision, better than
  either option I sketched.

## Remaining findings — both are self-contradictions between corrected and uncorrected text

### R1. MINOR — §2.2 line 201 still carries the OLD reserved-key list

Your reply says "Section 0 and section 2.2 now state the control-mode reserve set as
esc, enter, prefix, 1..9, plus all four arrows". §0 (lines 66-73) says exactly that.
But §2.2 still reads: "Reserved and non-configurable inside the mode: `esc`, `enter`,
`1..9`, the prefix key." — no arrows. Since §2.2 is the section an implementer will
have open while writing the keymap and the config docs, the stale list re-creates the
original finding-4 ambiguity inside the same document. Correction: make §2.2's
reserved sentence identical to §0's (esc, enter, prefix, 1..9, all four arrows;
tab/backtab deliberately not reserved).

### R2. MINOR — §3 still claims `just check`'s maintenance scripts cover translation parity

§3 (Testing strategy): "Maintenance scripts cover config-reference parity, translation
parity, changelog shape, and vendored-patch hygiene, so docs debt fails fast." This is
the pre-round-1 sentence and now contradicts both the corrected §0 bullet
("fixture-only" in `just test`) and Phase 4's corrected test section. Correction: drop
"translation parity" from that list or qualify it the way §0 does; as written, a
reader of §3 alone re-inherits the false belief finding 5 removed.

## Convergence status

Nothing else remains. Both residual items are one-sentence edits to text your round-1
reply already claimed to have changed — no new verification is needed on my side once
the sentences match §0. If your next reply confirms those two edits (or rebuts with a
reading I've missed), I will declare convergence.
