# imp_message_1 - round 1 reply

All findings accepted after independent re-verification on this host (B1, M1-M4
verified structurally and by re-running `cp -R` nesting, `$SHELL`/`~/.zshrc`/
`~/.config/fish`, brew deprecate/disable dates, `xcrun --show-sdk-version`,
`~/.profile` presence). No refutations this round. Exact diffs are at the bottom;
every claim below points at them.

## Dispositions

- **B1 (BLOCKER, smoke test after overwrite)** - FIXED. `target/release/herdr
  --version` now runs BEFORE `install`; install goes to `$INSTALL_DIR/.herdr.new`
  then `mv` (closes m2 too). Verify item added and RUN: stub `cargo` emitting a
  `target/release/herdr` that exits 1 -> section exits 1, pre-existing install
  still runs (`OLD-GOOD`); good artifact -> replaced, no `.herdr.new` left.
- **M1 (`.tmp` trap)** - FIXED: `rm -rf "$ziglib.tmp"` before the `cp -R`. Verify
  item added and RUN: pre-created `zig-lib-0.15.2-patched.tmp/junk` in a scratch
  `DATA_DIR`, section succeeds, header patched, rerun no-op.
- **M2 (distro cargo defeats the pin)** - FIXED: gate is now `! command -v rustup
  && [ ! -x ~/.cargo/bin/cargo ]`; `~/.cargo/bin` is always prepended. PLAN.md
  Verified-facts line rewritten to "only a rustup-managed cargo honors the pin"
  with the debian bookworm cargo 0.66 / Cargo.lock v4 evidence.
- **M3 (`$SHELL` misdetects fish)** - FIXED, option (a): `~/.config/fish` dir +
  `fish` on PATH is checked first, then `$SHELL`. Verify item added and RUN:
  `$SHELL=/bin/zsh` with a fish config dir takes the fish branch, writes
  `fish_user_paths`, creates no `.zshrc`.
- **M4 (`[x]` overstates macOS coverage)** - FIXED: reworded to "macOS with brew
  zig and rustup already present, fresh zig caches ... NOT cold-machine coverage";
  new open item "macOS cold path (no rustup, no brew zig, no ~/.local/bin) -
  unverified; needs a throwaway macOS user or Tart VM".
- **m1 (temp extraction dirs)** - FIXED: `trap 'rm -rf "$tmp"' EXIT`; `rmdir`
  dropped (nit 3 moot). Exercised by the debian stub harness: no `.zig-*` left.
- **m2 (GNU install non-atomic)** - FIXED with B1 (`.herdr.new` + `mv`).
- **m3 (substring guard)** - FIXED: `grep -qsxF "$line"`. Verify RUN: a
  pre-existing `.local/bin/other` line no longer suppresses the append; rerun once.
- **m4 (macOS bash shadows .profile)** - FIXED: prefer existing `.bash_profile`,
  else append to existing `.profile`, else create `.bash_profile`. Verify RUN:
  existing `.profile` gets the line appended, no `.bash_profile` created; with
  neither present, `.bash_profile` is created.
- **m5 (HOMEBREW_NO_AUTO_UPDATE)** - FIXED.
- **m6 (no `cc` preflight on macOS)** - FIXED: `need cc` moved out of the Linux
  arm, runs on both.
- **m7 (lib copies accumulate)** - ACCEPTED as a cache; stated in the plan.
- **m8 (Alpine contradiction)** - FIXED: plan now says Alpine/musl is a NON-GOAL
  per the intent record; the earlier alpine evidence is noted as incidental; the
  "need cc/xz messages name the missing tools" clause is no longer attached to
  alpine. Not a scope change - the intent record rules.
- **m9 (decisions log / DATA_DIR proposal)** - FIXED: Phase 8 decisions-log entry
  added (brew vs tarball, DATA_DIR proceeding under PROPOSAL, shell detection,
  smoke-before-install, no-checksum decision, non-goals); intent record's open
  item now says "proceeding under it; owner may override".
- **m10 (in-app updater clobbers fork build)** - FIXED: Verified-facts bullet
  added naming `src/update.rs auto_update`; "do not accept in-app updates on a
  fork build".
- **m11 (brew deprecate/disable dates)** - FIXED: dates added next to the zig
  0.16 removal condition.
- **NITs**: (1) fish quoting - left as is; (2) symlinked invocation - left as is;
  (3) `rmdir` - removed (trap cleans); (4) no checksum - recorded as a decision in
  the decisions log.

## Also done this round
- Your stub-cargo harness adopted as the Linux install/PATH gate (stub at
  `~/.cargo/bin/cargo` so the script's own `PATH` prepend picks it up): debian
  full path twice, exit 0 both, `~/.bashrc` exactly one line, no `.zig-*`
  leftovers, installed stub runs. Recorded as `[x]` with the method in the
  stress-test strategy.
- Leftover sweep over the touched tokens (`command -v cargo`, `rmdir`, "cargo not
  found", "need cc; need xz", "by $SHELL", the alpine "supported" clause, the old
  macOS `[x]` wording): no stale sites in PLAN.md, the script, or the intent record.

## Exact diffs (vs commit ea25571a, the state you reviewed)

### build_and_install.sh
```diff
diff --git a/build_and_install.sh b/build_and_install.sh
index 47f612e0..3db9d413 100755
--- a/build_and_install.sh
+++ b/build_and_install.sh
@@ -1,8 +1,8 @@
 #!/usr/bin/env bash
 # Build herdr from this checkout and install it to ~/.local/bin.
 #
-# - Installs Rust via rustup if cargo is missing (rust-toolchain.toml pins the
-#   exact toolchain; rustup fetches it on first use).
+# - Installs Rust via rustup if rustup is missing (rust-toolchain.toml pins the
+#   exact toolchain; rustup honors it on first use - a distro cargo would not).
 # - Zig 0.15 for the vendored libghostty-vt (build.rs shells out to $ZIG).
 #   macOS uses Homebrew's zig@0.15: it backports the MachO linker fix for
 #   Xcode 26.4+ SDKs (libSystem.tbd only lists arm64e now), which the official
@@ -23,25 +23,25 @@ need() {
 
 case "$(uname -s)" in
     Darwin) os=macos; need brew; need perl ;;
-    Linux) os=linux; need cc; need xz ;;  # cc links the Rust crates; xz unpacks zig
+    Linux) os=linux; need xz ;;  # xz unpacks the zig tarball
     *) echo "unsupported OS: $(uname -s)" >&2; exit 1 ;;
 esac
+need cc  # links the Rust crates
 need curl
 need tar
 
 # --- rust ---------------------------------------------------------------------
-if ! command -v cargo >/dev/null 2>&1; then
-    if [ ! -x "$HOME/.cargo/bin/cargo" ]; then
-        echo "cargo not found; installing Rust via rustup"
-        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
-    fi
-    export PATH="$HOME/.cargo/bin:$PATH"
+# Gate on rustup, not cargo: only a rustup-managed cargo honors the toolchain pin.
+if ! command -v rustup >/dev/null 2>&1 && [ ! -x "$HOME/.cargo/bin/cargo" ]; then
+    echo "rustup not found; installing Rust via rustup"
+    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
 fi
+export PATH="$HOME/.cargo/bin:$PATH"
 
 # --- zig ----------------------------------------------------------------------
 mkdir -p "$DATA_DIR"
 if [ "$os" = macos ]; then
-    brew list zig@0.15 >/dev/null 2>&1 || brew install zig@0.15
+    brew list zig@0.15 >/dev/null 2>&1 || HOMEBREW_NO_AUTO_UPDATE=1 brew install zig@0.15
     zig_prefix="$(brew --prefix zig@0.15)"
     zig_ver="$("$zig_prefix/bin/zig" version)"
     # The macOS 26 SDK no longer exposes INFINITY to zig 0.15's bundled libcxx,
@@ -51,6 +51,7 @@ if [ "$os" = macos ]; then
     ziglib="$DATA_DIR/zig-lib-$zig_ver-patched"
     if [ ! -d "$ziglib" ]; then
         echo "creating patched copy of zig $zig_ver lib dir at $ziglib"
+        rm -rf "$ziglib.tmp"
         cp -R "$zig_prefix/lib/zig" "$ziglib.tmp"
         perl -0pi -e 's/_LIBCPP_BEGIN_NAMESPACE_STD/#ifndef INFINITY\n#  define INFINITY __builtin_inff()\n#endif\n\n_LIBCPP_BEGIN_NAMESPACE_STD/' \
             "$ziglib.tmp/libcxx/include/__random/clamp_to_integral.h"
@@ -69,11 +70,11 @@ else
     if [ ! -x "$zig_dir/zig" ]; then
         echo "fetching zig $ZIG_VERSION into $DATA_DIR"
         tmp="$(mktemp -d "$DATA_DIR/.zig-XXXXXX")"
+        trap 'rm -rf "$tmp"' EXIT
         curl --proto '=https' --tlsv1.2 -sSfL \
             "https://ziglang.org/download/$ZIG_VERSION/zig-$arch-linux-$ZIG_VERSION.tar.xz" \
             | tar -xJ -C "$tmp"
         mv "$tmp/zig-$arch-linux-$ZIG_VERSION" "$zig_dir"
-        rmdir "$tmp"
     fi
     zig="$zig_dir/zig"
 fi
@@ -81,9 +82,12 @@ export ZIG="$zig"
 
 # --- build + install ----------------------------------------------------------
 cargo build --release --locked
+# Smoke-test the artifact before it touches the live install; then replace
+# atomically so an interrupted copy cannot leave a truncated binary.
+target/release/herdr --version
 install -d "$INSTALL_DIR"
-install -m 755 target/release/herdr "$INSTALL_DIR/herdr"
-"$INSTALL_DIR/herdr" --version
+install -m 755 target/release/herdr "$INSTALL_DIR/.herdr.new"
+mv "$INSTALL_DIR/.herdr.new" "$INSTALL_DIR/herdr"
 echo "installed to $INSTALL_DIR/herdr"
 
 # --- PATH ---------------------------------------------------------------------
@@ -91,8 +95,15 @@ case ":$PATH:" in
     *":$INSTALL_DIR:"*) exit 0 ;;
 esac
 
+# $SHELL is the passwd login shell, which often stays zsh/bash while the user
+# actually runs fish; a fish config dir is the better signal.
+if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
+    shell=fish
+else
+    shell="$(basename "${SHELL:-}")"
+fi
 line='export PATH="$HOME/.local/bin:$PATH"'
-case "$(basename "${SHELL:-}")" in
+case "$shell" in
     fish)
         # fish_add_path exits 1 when nothing was added, so guard for reruns.
         fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
@@ -100,13 +111,21 @@ case "$(basename "${SHELL:-}")" in
         exit 0
         ;;
     zsh) rc="$HOME/.zshrc" ;;
-    bash) [ "$os" = macos ] && rc="$HOME/.bash_profile" || rc="$HOME/.bashrc" ;;
+    bash)
+        rc="$HOME/.bashrc"
+        if [ "$os" = macos ]; then
+            # Login shells read only the first of .bash_profile/.bash_login/.profile;
+            # creating .bash_profile next to an existing .profile would shadow it.
+            rc="$HOME/.bash_profile"
+            [ -f "$rc" ] || [ ! -f "$HOME/.profile" ] || rc="$HOME/.profile"
+        fi
+        ;;
     *)
         echo "add $INSTALL_DIR to your PATH, e.g.: $line"
         exit 0
         ;;
 esac
-if ! grep -qsF '.local/bin' "$rc"; then
+if ! grep -qsxF "$line" "$rc"; then
     printf '\n%s\n' "$line" >> "$rc"
     echo "added $INSTALL_DIR to PATH in $rc (open a new shell)"
 fi
```

### PLAN.md (Phase 8 + decisions log)
```diff
diff --git a/PLAN.md b/PLAN.md
index 9f205ed4..ae08eb24 100644
--- a/PLAN.md
+++ b/PLAN.md
@@ -762,19 +762,23 @@ zoom, `p` joining `t/s/a` as the in-mode scope hop. No new machinery: one more
 
 ### Phase 8 - build_and_install.sh (source build + install for the fork)
 
-**Goal**: one script at the repo root that takes a fresh macOS or Linux box to
-`~/.local/bin/herdr` built from this checkout: Rust via rustup if missing, the
-right zig 0.15 for the vendored libghostty-vt, the binary installed, and
-`~/.local/bin` put on PATH for the user's shell. Supersedes the git-excluded
-`build_and_install_local.sh`.
-
-**Verified facts (2026-08-22, this host: macOS 26.5.2, Xcode-beta 27.0 SDK +
-CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU)**
+**Goal**: one script at the repo root that takes a fresh macOS or Linux glibc box
+to `~/.local/bin/herdr` built from this checkout: Rust via rustup if missing, the
+right zig 0.15 for the vendored libghostty-vt, the binary installed without ever
+leaving a broken one over a working install, and `~/.local/bin` put on PATH for
+the shell the user actually runs. Supersedes the git-excluded
+`build_and_install_local.sh`. Intent record: `research/intent.md`.
+
+**Verified facts (2026-08-22/23, this host: macOS 26.5.2, Xcode-beta 27.0 SDK +
+CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
 - `build.rs` runs `$ZIG build ...` (falls back to `zig` on PATH); CI pins zig
-  0.15.2 (mlugg/setup-zig on Linux, `brew install zig@0.15` on macOS).
-  `rust-toolchain.toml` pins 1.96.1, so rustup fetches the exact toolchain on
-  first `cargo` call; no version logic belongs in the script. `cmake`/`ninja`
-  from CI are not herdr dependencies (absent from Cargo.lock).
+  0.15.2 (mlugg/setup-zig on Linux, `HOMEBREW_NO_AUTO_UPDATE=1 brew install
+  zig@0.15` on macOS). `rust-toolchain.toml` pins 1.96.1 and rustup honors it on
+  first `cargo` call - but ONLY a rustup-managed cargo does: a distro cargo
+  (debian bookworm ships cargo 0.66/rustc 1.63, which cannot even parse this
+  `Cargo.lock` v4) ignores the pin, so the script gates on `rustup`, not `cargo`,
+  and prepends `~/.cargo/bin`. `cmake`/`ninja` from CI are not herdr dependencies
+  (absent from Cargo.lock).
 - **The official zig 0.15.2 macOS tarball cannot link on current macOS.** Since
   Xcode 26.4 Apple's `libSystem.tbd` lists only `arm64e-macos` (no
   `arm64-macos`; true of both the CLT 26.5 and the Xcode-beta 27.0 SDK). zig
@@ -785,61 +789,99 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU)**
   Zig on macOS". Proof: fresh-cache `zig build-exe hello.zig` exits 1 with the
   tarball, 0 with brew's zig; identical `zig ld` lines. A warm `~/.cache/zig`
   masks this completely (the build runner is a cache hit), so any macOS test
-  must use fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`.
-- The macOS 26 SDK INFINITY/libcxx problem from section 0 still applies on top:
-  a private patched copy of the lib dir (now under `~/.local/share/herdr`, never
-  the keg, keyed by `zig version`) plus a one-line wrapper exported as `ZIG`.
-- Linux: the official tarball is fine; the build additionally needs a C
-  compiler/linker for the Rust crates (`linker cc not found` otherwise) and `xz`
-  for the tarball. rustup's cargo on Alpine/musl also needs `libgcc`.
-- `fish_add_path -U` exits 1 when nothing was added; rustup's own profile edits
-  are skipped (`--no-modify-path`) and `~/.cargo/bin` is only prepended for the
-  run.
+  must use fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`. The brew formula
+  is `deprecate! 2027-04-15` / `disable! 2028-04-15`: after that date the macOS
+  branch stops working unless upstream has moved to zig 0.16 (herdrdev/herdr#285).
+- The macOS 26 SDK INFINITY/libcxx problem from section 0 still applies on top
+  (confirmed: unpatched brew zig fails `sub-compilation of libcxx ...
+  clamp_to_integral.h: use of undeclared identifier 'INFINITY'`): a private
+  patched copy of the lib dir (209 MB / 18,101 files, under
+  `~/.local/share/herdr`, never the keg, keyed by `zig version`) plus a one-line
+  wrapper exported as `ZIG`. Copies for superseded zig point releases are NOT
+  pruned - accepted, it is a cache; delete old `zig-lib-*-patched` dirs by hand.
+- Linux: the official tarball is fine (`zig-<arch>-linux-0.15.2.tar.xz`, 200 for
+  both arches; the pre-0.14 spelling 404s); the build additionally needs a C
+  compiler/linker for the Rust crates (`linker cc not found` otherwise) and
+  `xz` for the tarball. `need cc` runs on both platforms (macOS CLT can be
+  absent or its SDK broken, as `xcrun --show-sdk-version` is on this host today).
+- `install(1)` replaces atomically on macOS but GNU `install` unlinks first, so
+  the script installs to `.herdr.new` and `mv`s; macOS and Linux both leave a
+  running herdr process undisturbed (inode changes, confirmed both sides).
+- `$SHELL` is the passwd login shell, not the interactive one: on this host it
+  is `/bin/zsh` while the owner runs fish with a populated `fish_user_paths`
+  and no `~/.zshrc`. A `~/.config/fish` dir plus `fish` on PATH is the better
+  signal and is checked first. bash login shells read only the first of
+  `.bash_profile`/`.bash_login`/`.profile`, so on macOS an existing `.profile`
+  is appended to rather than shadowed by a new `.bash_profile`.
+- `fish_add_path -U` exits 1 when nothing was added (fish 4.8.1); rustup's own
+  profile edits are skipped (`--no-modify-path`).
+- After this script installs a fork build, herdr's in-app updater
+  (`src/update.rs` `auto_update`) will still offer upstream releases; accepting
+  one replaces the control-mode patch series. Do not accept in-app updates on a
+  fork build (section 0 already warns about `herdr update`).
 
 **Implement**
-1. [x] `build_and_install.sh`: tool preflight (`brew`+`perl` on macOS; `cc`+`xz`
-   on Linux; `curl`, `tar`) with "missing required tool: X" messages; rustup if
-   no cargo; macOS: `brew install zig@0.15` + patched lib copy + wrapper; Linux:
-   official tarball extracted atomically (temp dir then `mv`) into
-   `~/.local/share/herdr`; `cargo build --release --locked`; install; PATH by
-   `$SHELL` (fish universal var, zsh `~/.zshrc`, bash `~/.bash_profile` on macOS
-   / `~/.bashrc` on Linux, otherwise print the export line), duplicate-guarded,
-   skipped when already on PATH.
+1. [x] `build_and_install.sh`: tool preflight (`brew`+`perl` on macOS; `xz` on
+   Linux; `cc`, `curl`, `tar` everywhere) with "missing required tool: X"
+   messages; rustup if no `rustup`; macOS: `brew install zig@0.15` (no
+   auto-update) + patched lib copy (stale `.tmp` removed first, built in
+   `.tmp`, then `mv`) + wrapper; Linux: official tarball extracted into a
+   `mktemp` dir with an EXIT trap, then `mv`; `cargo build --release --locked`;
+   smoke-test `target/release/herdr --version` BEFORE touching the install;
+   install to `.herdr.new` and `mv`; PATH by detected shell (fish config dir
+   first, else `$SHELL`): fish universal var, zsh `~/.zshrc`, bash
+   `~/.bash_profile`-or-existing-`~/.profile` on macOS / `~/.bashrc` on Linux,
+   otherwise print the export line; exact-line duplicate guard; skipped when
+   already on PATH.
 
 **Stress-test strategy (how to test without touching the real system)**
 - Linux: Docker containers from clean images, script copied in and run as a
-  fresh user would (`debian:bookworm-slim`, `fedora:latest`, `alpine:3.21`;
-  `--platform linux/amd64` available via emulation for the x86_64 URL path).
-  Vary what is preinstalled (no curl, no cc, no xz) to exercise the preflight.
-- macOS (no containers): the real-system risks are the zig cache mirage and the
-  shell rc files. Run the script with fresh `ZIG_GLOBAL_CACHE_DIR` and
-  `ZIG_LOCAL_CACHE_DIR` (temp dirs); test the PATH section in isolation by
-  extracting it into a throwaway `$HOME` with `$SHELL` set to each shell and
-  rerun for idempotency. A fake `$HOME` is NOT valid for the full build (rustup,
-  cargo, and zig all key off it). Gold standard when wanted: a throwaway macOS
-  user (`sysadminctl -addUser`, needs sudo) or a Tart VM.
+  fresh user would (`debian:bookworm-slim`, `fedora:latest`; `--platform
+  linux/amd64` available via emulation for the x86_64 URL path). Vary what is
+  preinstalled (no curl, no cc, no xz) to exercise the preflight. The 2 GB
+  Docker cap kills the final `rustc` of the herdr crate (2.1 GB peak RSS), so
+  the install/PATH half is exercised with a stub `~/.cargo/bin/cargo` that
+  checks `$ZIG` and emits a fake `target/release/herdr` - real zig download,
+  real extraction, real install, real rc edits.
+- macOS (no containers): the real-system risks are the zig cache mirage, the
+  live `~/.local/bin/herdr`, and the shell rc files. Run the full script only
+  with fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`; test the PATH,
+  install, and zig sections in isolation by extracting them into a throwaway
+  `$HOME`/`DATA_DIR`/cwd with stub `cargo` and stub artifacts. A fake `$HOME`
+  is NOT valid for the full build (rustup, cargo, and zig all key off it). Gold
+  standard for the cold path: a throwaway macOS user (`sysadminctl -addUser`,
+  needs sudo) or a Tart VM.
 
 **Verify**
-- [x] macOS, fresh zig caches: full run builds libghostty from scratch
-      (1m17s), installs, `herdr --version` ok; rerun idempotent.
-- [x] PATH section: zsh/bash append once with guard; fish writes
-      `fish_user_paths`; unknown shell prints the hint; reruns no-op.
+- [x] macOS with brew zig and rustup already present, fresh zig caches: full
+      run builds libghostty from scratch (1m17s), installs, `herdr --version`
+      ok; rerun idempotent. This is NOT cold-machine coverage (see open item).
+- [x] Live-install gate: with a stub `cargo` producing a `target/release/herdr`
+      that exits 1, the build+install section exits 1 and the pre-existing
+      install still runs; with a good artifact it is replaced and no
+      `.herdr.new` remains.
+- [x] Zig section: a pre-existing `zig-lib-*-patched.tmp` (interrupted copy)
+      no longer traps the rerun; the patched header is present; rerun no-op.
+- [x] PATH section: detection - `$SHELL=/bin/zsh` with a `~/.config/fish` dir
+      takes the fish branch and writes `fish_user_paths`, no `.zshrc` created;
+      zsh appends once (exact-line guard: a pre-existing
+      `.local/bin/other` line no longer suppresses it); bash on macOS appends
+      to an existing `~/.profile` and creates `~/.bash_profile` only when
+      neither exists; unknown shell prints the hint; reruns no-op.
 - [x] Linux preflight: debian without a compiler stops at
       "missing required tool: cc" (no mid-script `command not found`).
-- [x] Linux, Docker matrix (debian:bookworm-slim, fedora:latest, alpine:3.21,
-      with cc/xz/curl; alpine also libgcc+build-base): rustup install, zig
-      tarball fetch, libghostty-vt build, and all 149 dependency crates succeed
-      on every image; the FINAL `rustc` of the herdr crate is SIGKILLed in all
-      three - including alone with `CARGO_BUILD_JOBS=1` - because Docker
-      Desktop here is capped at 2.0 GB while that single compile peaks at
-      2.1 GB RSS on the host. Environmental, not a script defect; a full Linux
-      pass needs Docker Desktop memory raised to >= 4 GB (user setting).
-- [ ] Linux end-to-end green once Docker memory is raised (rerun the matrix,
-      one container at a time). Alpine/musl builds identically up to that
-      point, so it is supported given `libgcc` + `build-base`; the script's
-      `need cc`/`need xz` messages name the missing tools.
-- [ ] Adversarial round via keemakr-long-yolo-harden-plan (needs a Herdr pane:
-      HERDR_ENV=1, intent record backfill).
+- [x] Linux stub-cargo harness, debian:bookworm-slim (stub `~/.cargo/bin/cargo`
+      checks `$ZIG`, emits a fake artifact): full script path twice - real zig
+      fetch, EXIT-trap leaves no `.zig-*` dir, install + atomic replace,
+      `~/.bashrc` gains exactly one line, second run is a no-op, exit 0 both.
+- [ ] Linux end-to-end compile (debian + fedora) once Docker Desktop memory is
+      raised to >= 4 GB (user setting); everything up to the final rustc is
+      already green on both. Alpine/musl is a NON-GOAL per the intent record
+      (earlier runs built identically up to the same point; not supported).
+- [ ] macOS cold path (no rustup, no brew zig, no `~/.local/bin`) - unverified;
+      needs a throwaway macOS user or a Tart VM. [needs a human or sudo]
+- [ ] Adversarial loop via keemakr-long-yolo-harden-plan
+      (`adv_convo_1787423967261/`) converged.
 
 ## 5. Decisions log / open questions
 
@@ -874,6 +916,16 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU)**
   SwitchTab, spaces -> SwitchWorkspace, agents -> FocusAgent), reserved and
   hardwired. [Superseded the single-mode-era "tabs only" wording in the round-3
   audit; the scoped behavior is what Phase 6 shipped, documented, and tests.]
+- Phase 8 build script: brew `zig@0.15` over the official tarball on macOS
+  (tarball cannot link on Xcode 26.4+ SDKs; brew backports the fix; dated
+  deprecate/disable 2027/2028). `~/.local/share/herdr` as the toolchain home
+  (zig tarball, patched lib copy, wrapper) - proceeding under PROPOSAL, owner
+  may override (intent record, open item). Shell detection: `~/.config/fish`
+  dir first, then `$SHELL` (the passwd shell misdetects the owner's own Mac).
+  Smoke-test before install, atomic replace - the "never break my installed
+  herdr" ruling. The zig tarball is fetched WITHOUT a checksum (TLS plus
+  xz/tar integrity; the official installer does verify its binary) - a decision,
+  not an oversight. Alpine/musl and Windows are non-goals.
 - Open: whether upstream wants `control_*` flat keys or a `[keys.control]` table.
   Flat matches `navigate_*` precedent; a table reads better but changes the
   config-reference model walk. Decide at Discussion time; local build ships flat.
```

### research/intent.md
```diff
diff --git a/research/intent.md b/research/intent.md
index 6861b07a..ba886243 100644
--- a/research/intent.md
+++ b/research/intent.md
@@ -71,5 +71,5 @@ ruling) / PROPOSAL (my default, owner may override).
 - PROPOSAL: the Docker-based Linux matrix is the Linux verification gate; the
   owner may raise Docker Desktop memory (>= 4 GB) to let it run green, or
   accept the current "everything but the final 2.1 GB rustc" evidence.
-- PROPOSAL: `~/.local/share/herdr` as the home for the zig tarball / patched
-  lib copy / wrapper (XDG data dir); owner may prefer another location.
+- PROPOSAL (proceeding under it; owner may override): `~/.local/share/herdr`
+  as the home for the zig tarball / patched lib copy / wrapper (XDG data dir).
```
