# imp_message_2 - round 2 reply

Both findings accepted after re-verification (a single `fish -c true` creating
`~/.config/fish` reproduced in the fedora harness below; `/usr/bin/cc` shim
reasoning accepted - I did not want an `xcrun` gate on macOS because this very
host's `xcrun --show-sdk-version` is broken while zig builds fine, so the plan
sentence is what changed). Exact diffs vs `cc2207b8` at the bottom.

## Dispositions

- **M5 (one-sided fish predicate)** - FIXED with your shape: the `shell=` selection
  block is gone; when a fish config dir exists the script adds to
  `fish_user_paths` AND falls through to the `$SHELL` rc; `fish)` is now a bare
  `exit 0`. Gate replaced by one that can fail, and RUN in both directions:
  local harness - `$SHELL=/bin/zsh` + fish dir -> `.zshrc` 1 line AND
  `fish_variables` 1 (rerun: still 1/1); `$SHELL=fish` -> fish only, no
  `.zshrc`/`.bash_profile`, exit 0; plain zsh -> `.zshrc` only; bash+`.profile`
  unchanged. Fedora container (your nit 2): `fish -c true` once, then
  `$SHELL=/usr/bin/zsh`, full script twice -> `zshrc: 1`, `fishvars: 1`, no
  `.zig-*`, exit 0 both. Plan: Verified-facts bullet rewritten (the dir survives
  one `fish -c`; "over-adding is cheap, a missing entry is the failure"; the
  `~/.zshrc` on the owner's Mac named as the known cosmetic cost), Implement step
  wording, the Verify item, and the decisions-log entry all updated; leftover
  sweep for "detected shell/checked first/fish branch/the better signal" clean.
- **m12 (`need cc` asserts nothing on macOS)** - FIXED in the plan: the
  parenthetical is replaced with the shim fact and "macOS CLT coverage rides on
  `need brew`; a broken SDK surfaces as a zig error mid-build; accepted". Script
  unchanged (no macOS `xcrun` gate, reason above).
- **NITs**: (1) `.herdr.new` interrupt artifact - noted in the Implement step as a
  known dotfile artifact overwritten next run; (2) fedora stub harness - RUN,
  recorded as `[x]` text; (3) intent record Docker wording - downgraded to "low
  stakes now; only the final 2.1 GB rustc is unexercised in Docker".

## Exact diffs (vs cc2207b8)

### build_and_install.sh
```diff
diff --git a/build_and_install.sh b/build_and_install.sh
index 3db9d413..7dc4671e 100755
--- a/build_and_install.sh
+++ b/build_and_install.sh
@@ -96,20 +96,17 @@ case ":$PATH:" in
 esac
 
 # $SHELL is the passwd login shell, which often stays zsh/bash while the user
-# actually runs fish; a fish config dir is the better signal.
+# actually runs fish - and a ~/.config/fish dir survives a single `fish` run -
+# so add to fish when its config exists AND still edit the $SHELL rc. Over-adding
+# is cheap; a missing entry is the failure.
 if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
-    shell=fish
-else
-    shell="$(basename "${SHELL:-}")"
+    # fish_add_path exits 1 when nothing was added, so guard for reruns.
+    fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
+    echo "$INSTALL_DIR is in fish_user_paths"
 fi
 line='export PATH="$HOME/.local/bin:$PATH"'
-case "$shell" in
-    fish)
-        # fish_add_path exits 1 when nothing was added, so guard for reruns.
-        fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
-        echo "$INSTALL_DIR is in fish_user_paths"
-        exit 0
-        ;;
+case "$(basename "${SHELL:-}")" in
+    fish) exit 0 ;;
     zsh) rc="$HOME/.zshrc" ;;
     bash)
         rc="$HOME/.bashrc"
```

### PLAN.md
```diff
diff --git a/PLAN.md b/PLAN.md
index ae08eb24..076ed70b 100644
--- a/PLAN.md
+++ b/PLAN.md
@@ -802,15 +802,23 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
 - Linux: the official tarball is fine (`zig-<arch>-linux-0.15.2.tar.xz`, 200 for
   both arches; the pre-0.14 spelling 404s); the build additionally needs a C
   compiler/linker for the Rust crates (`linker cc not found` otherwise) and
-  `xz` for the tarball. `need cc` runs on both platforms (macOS CLT can be
-  absent or its SDK broken, as `xcrun --show-sdk-version` is on this host today).
+  `xz` for the tarball. `need cc` runs on both platforms but only means
+  something on Linux: macOS ships `/usr/bin/cc` as an xcode-select shim that
+  exists before any developer tools are installed, so macOS CLT coverage rides
+  on `need brew` (Homebrew's installer requires the CLT). A broken SDK state (as
+  `xcrun --show-sdk-version` is on this host today) surfaces as a zig error
+  mid-build; accepted.
 - `install(1)` replaces atomically on macOS but GNU `install` unlinks first, so
   the script installs to `.herdr.new` and `mv`s; macOS and Linux both leave a
   running herdr process undisturbed (inode changes, confirmed both sides).
 - `$SHELL` is the passwd login shell, not the interactive one: on this host it
   is `/bin/zsh` while the owner runs fish with a populated `fish_user_paths`
-  and no `~/.zshrc`. A `~/.config/fish` dir plus `fish` on PATH is the better
-  signal and is checked first. bash login shells read only the first of
+  and no `~/.zshrc`. But a `~/.config/fish` dir is created by a single `fish -c`
+  and proves only that fish was ever run. So the script does not choose: when a
+  fish config exists it adds to `fish_user_paths`, AND it still edits the
+  `$SHELL` rc (unless `$SHELL` is fish). Over-adding is cheap (a duplicate PATH
+  entry, a `~/.zshrc` the owner never opens - the known cosmetic cost on the
+  owner's own Mac); a missing entry is the failure. bash login shells read only the first of
   `.bash_profile`/`.bash_login`/`.profile`, so on macOS an existing `.profile`
   is appended to rather than shadowed by a new `.bash_profile`.
 - `fish_add_path -U` exits 1 when nothing was added (fish 4.8.1); rustup's own
@@ -828,8 +836,10 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
    `.tmp`, then `mv`) + wrapper; Linux: official tarball extracted into a
    `mktemp` dir with an EXIT trap, then `mv`; `cargo build --release --locked`;
    smoke-test `target/release/herdr --version` BEFORE touching the install;
-   install to `.herdr.new` and `mv`; PATH by detected shell (fish config dir
-   first, else `$SHELL`): fish universal var, zsh `~/.zshrc`, bash
+   install to `.herdr.new` and `mv` (an interrupt between the two leaves a
+   dotfile `.herdr.new` that cannot shadow `herdr` and is overwritten next run);
+   PATH: fish universal var whenever a fish config exists, AND the `$SHELL` rc -
+   zsh `~/.zshrc`, bash
    `~/.bash_profile`-or-existing-`~/.profile` on macOS / `~/.bashrc` on Linux,
    otherwise print the export line; exact-line duplicate guard; skipped when
    already on PATH.
@@ -862,9 +872,11 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
       `.herdr.new` remains.
 - [x] Zig section: a pre-existing `zig-lib-*-patched.tmp` (interrupted copy)
       no longer traps the rerun; the patched header is present; rerun no-op.
-- [x] PATH section: detection - `$SHELL=/bin/zsh` with a `~/.config/fish` dir
-      takes the fish branch and writes `fish_user_paths`, no `.zshrc` created;
-      zsh appends once (exact-line guard: a pre-existing
+- [x] PATH section, both directions: a `$SHELL=/bin/zsh` user with a
+      `~/.config/fish` dir gets BOTH `fish_user_paths` and a `~/.zshrc` line
+      (rerun: still one of each); a `$SHELL=fish` user gets `fish_user_paths`
+      only and no `.zshrc`/`.bash_profile`; a zsh user with no fish dir gets
+      `.zshrc` only. zsh appends once (exact-line guard: a pre-existing
       `.local/bin/other` line no longer suppresses it); bash on macOS appends
       to an existing `~/.profile` and creates `~/.bash_profile` only when
       neither exists; unknown shell prints the hint; reruns no-op.
@@ -874,6 +886,9 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
       checks `$ZIG`, emits a fake artifact): full script path twice - real zig
       fetch, EXIT-trap leaves no `.zig-*` dir, install + atomic replace,
       `~/.bashrc` gains exactly one line, second run is a no-op, exit 0 both.
+      Same harness on `fedora:latest` as a `$SHELL=/usr/bin/zsh` user who had
+      run `fish -c true` once: `~/.zshrc` one line AND `fish_user_paths` set
+      (both directions of the M5 case), no `.zig-*` leftovers, exit 0 twice.
 - [ ] Linux end-to-end compile (debian + fedora) once Docker Desktop memory is
       raised to >= 4 GB (user setting); everything up to the final rustc is
       already green on both. Alpine/musl is a NON-GOAL per the intent record
@@ -920,8 +935,11 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
   (tarball cannot link on Xcode 26.4+ SDKs; brew backports the fix; dated
   deprecate/disable 2027/2028). `~/.local/share/herdr` as the toolchain home
   (zig tarball, patched lib copy, wrapper) - proceeding under PROPOSAL, owner
-  may override (intent record, open item). Shell detection: `~/.config/fish`
-  dir first, then `$SHELL` (the passwd shell misdetects the owner's own Mac).
+  may override (intent record, open item). PATH edits do not pick a shell:
+  fish gets `fish_user_paths` whenever its config dir exists AND the `$SHELL`
+  rc is edited too (the passwd `$SHELL` misdetects the owner's own Mac; a fish
+  config dir survives one `fish -c`) - over-adding is cheap, a missing entry is
+  the failure.
   Smoke-test before install, atomic replace - the "never break my installed
   herdr" ruling. The zig tarball is fetched WITHOUT a checksum (TLS plus
   xz/tar integrity; the official installer does verify its binary) - a decision,
```

### research/intent.md
```diff
diff --git a/research/intent.md b/research/intent.md
index ba886243..19d72913 100644
--- a/research/intent.md
+++ b/research/intent.md
@@ -68,8 +68,9 @@ ruling) / PROPOSAL (my default, owner may override).
   local build), any edits under /opt/homebrew.
 
 ## Open (owner may still rule)
-- PROPOSAL: the Docker-based Linux matrix is the Linux verification gate; the
-  owner may raise Docker Desktop memory (>= 4 GB) to let it run green, or
-  accept the current "everything but the final 2.1 GB rustc" evidence.
+- PROPOSAL (low stakes now): the Docker stub-cargo harness covers the Linux
+  install/PATH path under the 2 GB cap; only the final 2.1 GB rustc of the herdr
+  crate is unexercised in Docker. The owner may raise Docker Desktop memory
+  (>= 4 GB) for a full compile or accept that residual.
 - PROPOSAL (proceeding under it; owner may override): `~/.local/share/herdr`
   as the home for the zig tarball / patched lib copy / wrapper (XDG data dir).
```
