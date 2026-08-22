# imp_message_3 - round 3 reply

**M6 - ACCEPTED, FIXED.** One token: `build_and_install.sh:102` now reads
`if [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/fish" ] && command -v fish ...`,
mirroring line 18. RUN locally (fish 4.8.1): `fish -c true` with
`XDG_CONFIG_HOME=$HOME/.dotcfg` created `.dotcfg/fish` and no `.config`; then
`$SHELL=fish` through the PATH section -> `fish_user_paths` set in
`.dotcfg/fish/fish_variables`, no `.zshrc`, rc=0. Regression: zsh + default fish
dir still gets both (1/1). PLAN.md Verify item gains the fourth case with the
"mirrors line 18" note. Sweep for a hardcoded `HOME/.config/fish` in the script
and plan: none left.

**NIT (fish -c failure aborts before the $SHELL rc)** - accepted as deliberate and
stated in the same Verify item: "If `fish -c` itself fails (read-only
`fish_variables`, fish < 3.2) `set -e` stops before the `$SHELL` rc is edited -
accepted, no error handling added."

## Exact diffs (vs c9cc4d16)

### build_and_install.sh
```diff
diff --git a/build_and_install.sh b/build_and_install.sh
index 7dc4671e..39ac0f60 100755
--- a/build_and_install.sh
+++ b/build_and_install.sh
@@ -99,7 +99,7 @@ esac
 # actually runs fish - and a ~/.config/fish dir survives a single `fish` run -
 # so add to fish when its config exists AND still edit the $SHELL rc. Over-adding
 # is cheap; a missing entry is the failure.
-if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
+if [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/fish" ] && command -v fish >/dev/null 2>&1; then
     # fish_add_path exits 1 when nothing was added, so guard for reruns.
     fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
     echo "$INSTALL_DIR is in fish_user_paths"
```

### PLAN.md
```diff
diff --git a/PLAN.md b/PLAN.md
index 076ed70b..782b5b9a 100644
--- a/PLAN.md
+++ b/PLAN.md
@@ -875,8 +875,12 @@ CLT 26.5 SDK, Docker Desktop 2 GB/2 CPU; re-verified by the round-1 adversary)**
 - [x] PATH section, both directions: a `$SHELL=/bin/zsh` user with a
       `~/.config/fish` dir gets BOTH `fish_user_paths` and a `~/.zshrc` line
       (rerun: still one of each); a `$SHELL=fish` user gets `fish_user_paths`
-      only and no `.zshrc`/`.bash_profile`; a zsh user with no fish dir gets
-      `.zshrc` only. zsh appends once (exact-line guard: a pre-existing
+      only and no `.zshrc`/`.bash_profile`; a `$SHELL=fish` user whose fish
+      config lives under a custom `XDG_CONFIG_HOME` still gets `fish_user_paths`
+      (the check mirrors line 18's `${XDG_...:-default}` form); a zsh user with
+      no fish dir gets `.zshrc` only. If `fish -c` itself fails (read-only
+      `fish_variables`, fish < 3.2) `set -e` stops before the `$SHELL` rc is
+      edited - accepted, no error handling added. zsh appends once (exact-line guard: a pre-existing
       `.local/bin/other` line no longer suppresses it); bash on macOS appends
       to an existing `~/.profile` and creates `~/.bash_profile` only when
       neither exists; unknown shell prints the hint; reruns no-op.
```
