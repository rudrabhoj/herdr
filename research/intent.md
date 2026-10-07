# Intent record: herdr fork build_and_install.sh (PLAN.md Phase 8)
Owner: Rudrabhoj Bhati. Source: this Claude session, 2026-08-22/23 (backfill
interview run by keemakr-long-yolo-harden-plan preflight against the existing
Phase 8). Tiers: RULED (owner said it, near-verbatim) / DERIVED (follows from a
ruling) / PROPOSAL (my default, owner may override).

## What is being built and why
- RULED: "create a build_and_install.sh script, it should make sure we have
  rust if not install it, and then get it into ~/.local/bin/herdr right, and if
  ~/.local/bin isn't in path, adds it depending upon the user's shell."
- RULED: it lives in the owner's fork `github.com/rudrabhoj/herdr`, which
  carries the control-mode patch series; upstream herdr is synced later,
  deliberately ("we want to update with master later not blind merge").
- RULED: "really deeply research first" - the script must be built on verified
  facts about how herdr actually builds (zig for libghostty-vt, toolchain pin),
  not assumptions.
- RULED: "what would be best way to really stress test it without ruining our
  local system" - the script must be exercised in isolation before it is
  trusted; the test strategy is part of the deliverable.

## Locked decisions
- RULED (owner, 2026-08-23): "Keep it short, no bloat" - "don't make code too
  complicated, use right logic, should have all this features without ai slop
  bloat". The adversary does not relitigate minimalism.
- RULED (owner, 2026-08-23 interview): using Homebrew on macOS is fine
  (requiring `brew` for zig@0.15 is acceptable).
- RULED (owner, 2026-08-23 interview): downloading rustup and zig from the
  internet is fine; no offline/air-gapped requirement.
- RULED (owner, standing rule + 2026-08-23 interview): must not modify anything
  under /opt/homebrew or any package-manager/system path; the patched zig lib
  copy stays private under `~/.local/share/herdr`.
- DERIVED: install target is exactly `~/.local/bin/herdr` (matches the
  official installer's default and the owner's existing install).

## Constraints
- RULED (2026-08-23 interview): platform matrix = macOS + Linux glibc
  (debian/fedora-class). Alpine/musl and Windows are non-goals.
- DERIVED: zig must be 0.16.x since the 2026-10-07 upstream sync (vendored
  `build.zig` requirement; CI pins 0.16.0, was 0.15.2); Rust toolchain is pinned by `rust-toolchain.toml` (1.96.1), so the
  script must not carry its own Rust version logic.
- DERIVED: the script runs from a git checkout of the fork (it `cd`s to its
  own directory and builds `--locked`).
- DERIVED: shells to support for PATH: fish (owner's shell), zsh, bash; other
  shells get a printed instruction.

## Cost of being wrong
- RULED (2026-08-23 interview): "Both, and it must never break my installed
  herdr" - fork users run this cold on fresh machines (a silent failure such as
  the warm-zig-cache mirage costs them hours), AND it runs on the owner's daily
  driver, where overwriting `~/.local/bin/herdr` with a broken binary is the
  unacceptable outcome.

## Prior art and rejections
- The git-excluded `build_and_install_local.sh` (brew zig@0.15 + patched lib
  dir copy inside the repo + wrapper): superseded; its approach for macOS zig
  was right, its repo-local copy and no Rust/PATH handling were not.
- REJECTED (by evidence, 2026-08-23): the official zig 0.15.2 macOS tarball -
  cannot link libSystem on Xcode 26.4+ SDKs (arm64e-only tbd); brew's
  `zig@0.15` carries the backported fix. SUPERSEDED 2026-10-07: zig 0.16.0
  (2026-04-13) ships that Mach-O fix (ziglang/zig#31673, merged 2026-03-27)
  and the macOS 26.4 headers, so the script now fetches the official tarball
  on both OSes and the brew/patched-lib path is gone.
- REJECTED: a fake `$HOME` as a full-build sandbox on macOS (rustup, cargo,
  zig all key off `$HOME`); valid only for the PATH section in isolation.
- REJECTED: the official installer's approach of merely printing a PATH hint -
  the owner asked for the PATH to be added per shell.

## Non-goals
- Windows, Alpine/musl, cross-compilation, offline installs, uninstall,
  updating an existing install via `herdr update` (which would clobber the
  local build), any edits under /opt/homebrew.

## Open (owner may still rule)
- PROPOSAL (low stakes now): the Docker stub-cargo harness covers the Linux
  install/PATH path under the 2 GB cap; only the final 2.1 GB rustc of the herdr
  crate is unexercised in Docker. The owner may raise Docker Desktop memory
  (>= 4 GB) for a full compile or accept that residual.
- PROPOSAL (proceeding under it; owner may override): `~/.local/share/herdr`
  as the home for the zig tarball / patched lib copy / wrapper (XDG data dir).
