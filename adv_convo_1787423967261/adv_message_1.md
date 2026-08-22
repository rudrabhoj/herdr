# adv_message_1 - Phase 8 + build_and_install.sh, round 1

Scope: `PLAN.md:763-842` and `build_and_install.sh` (112 lines, working-tree copy
as of 2026-08-23 00:09). Phases 0-7 and the decisions log are out of scope except
where Phase 8 contradicts them. I did not edit any repo file.

Everything below carries the command that produced it. I re-ran the two claims
the whole macOS design rests on, and both hold - read **What is sound** first, so
you fix the right things.

---

## What is sound (independently re-verified, do not touch)

These are not "I read it and it seemed fine". I re-ran them.

1. **"The official zig 0.15.2 macOS tarball cannot link on current macOS"
   (PLAN.md:778-788) - CONFIRMED.** Downloaded `zig-aarch64-macos-0.15.2.tar.xz`
   into a scratch dir, fresh `ZIG_GLOBAL_CACHE_DIR`/`ZIG_LOCAL_CACHE_DIR`, then
   `zig build-exe hello.zig`:
   ```
   error: undefined symbol: __availability_version_check
   error: undefined symbol: _abort
   error: undefined symbol: _bzero
   error: undefined symbol: _getenv ...
   ```
   Root cause corroborated at the source - both SDKs on this host list only
   `arm64e-macos`:
   ```
   $ head -3 /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/lib/libSystem.tbd
   targets:         [ x86_64-macos, x86_64-maccatalyst, arm64e-macos, arm64e-maccatalyst ]
   $ head -3 /Applications/Xcode-beta.app/.../MacOSX.sdk/usr/lib/libSystem.tbd
   targets:         [ x86_64-macos, x86_64-maccatalyst, arm64e-macos, arm64e-maccatalyst ]
   ```
   And `brew cat zig@0.15` carries exactly the fix you named, as its third
   `__END__` patch, on exactly the file you named:
   ```
   --- a/src/link/MachO/Dylib.zig
   @@ pub const TargetMatcher = struct {
   +        if (cpu_arch == .aarch64) try self.addTargetStrings("arm64e");
   ```
   The brew-over-tarball decision is correct and the reasoning is accurate.

2. **The INFINITY/libcxx problem (PLAN.md:789-791) - CONFIRMED.** Copied
   `vendor/libghostty-vt` to scratch, cleared `.zig-cache`/`zig-out`, ran the
   exact `build.rs` command line with the **unpatched** brew zig:
   ```
   error: sub-compilation of libcxx failed
       /opt/homebrew/Cellar/zig@0.15/0.15.2/lib/zig/libcxx/include/__random/clamp_to_integral.h:47:58:
       note: use of undeclared identifier 'INFINITY'
   ```
   The 209 MB private lib-dir copy is load-bearing, not cargo-culted.

3. **`fish_add_path -U` exits 1 when nothing was added (PLAN.md:795).**
   `fish -c 'fish_add_path -U ~/.local/bin; echo $status'` -> `1` on fish 4.8.1.
   The `contains ...; or fish_add_path -U ...` guard is the right shape.

4. **Linux preflight (PLAN.md:827-828) - CONFIRMED.**
   `docker run --rm -v .../build_and_install.sh:/tmp/bi.sh:ro debian:bookworm-slim bash /tmp/bi.sh`
   -> `missing required tool: cc`, rc=1, nothing else executed.

5. **macOS `install` is atomic and symlink-safe.** `man install`: *"Historically,
   -S also enabled the use of temporary files to ensure atomicity when replacing
   an existing target. Temporary files are no longer optional."* I confirmed the
   inode changes (18497272 -> 18497274), that installing over a **running**
   binary succeeds without disturbing the running process, and that a symlinked
   destination is **replaced**, not followed (so a prior mise-managed install is
   orphaned intact, not corrupted). Better than I expected going in.

6. **The `$ziglib` guard is on the final dir, not the temp**
   (`build_and_install.sh:52`), and `mv` is same-filesystem - so a half-copied lib
   dir can never be mistaken for a good one. Same shape on the Linux side
   (`mktemp -d` inside `$DATA_DIR`, then `mv`). Correct instinct. One hole: M1.

7. **No collision with herdr's own state.** Searching `src/` for `XDG_DATA_HOME`
   and `local/share` shows herdr never writes `~/.local/share/herdr`; the only
   hits are mise paths in tests. `$DATA_DIR` co-tenancy is safe.

8. **`--no-modify-path` + per-run `PATH` export (`:33-39`) is rerun-safe.** The
   second run finds `$HOME/.cargo/bin/cargo`, skips the rustup fetch, re-exports.

9. **Linux zig URL and arch mapping are right.**
   `curl -sSI https://ziglang.org/download/0.15.2/zig-x86_64-linux-0.15.2.tar.xz`
   -> `200`; `zig-aarch64-linux-0.15.2.tar.xz` -> `200`; the pre-0.14 spelling
   `zig-linux-x86_64-...` -> `404`. You picked the current naming.

---

## BLOCKER

### B1(r1) - BLOCKER, VERIFIED. The only gate against a broken binary runs *after* the live install has already been overwritten.

**Location**: `build_and_install.sh:83-87`.

```
83  cargo build --release --locked
84  install -d "$INSTALL_DIR"
85  install -m 755 target/release/herdr "$INSTALL_DIR/herdr"
86  "$INSTALL_DIR/herdr" --version
87  echo "installed to $INSTALL_DIR/herdr"
```

**Evidence.** The script's own smoke test is line 86 - after the destructive line
85. There is no pre-install check, no backup, no rollback. Contrast the prior art
the intent record cites as the source of the install target
(`research/intent.md:32-33`): `website/install.sh:91-110` downloads to
`mktemp -d`, verifies SHA-256, and only then `mv`s into `$INSTALL_DIR`. It never
places an unverified artifact over the existing one. Phase 8 inverts that
ordering and nothing in `PLAN.md:763-842` acknowledges the inversion.

**Failure scenario.** The audience for this script is a fork carrying an unmerged
control-mode patch series (`research/intent.md:11-13`), and Phase 7 still has
open manual items (`PLAN.md:759-761`). `cargo build --release` exits 0 for any
binary that *compiles*; it says nothing about one that starts. A binary that
panics on startup - a config-parse regression against the owner's existing
`~/.config/herdr/config.toml`, a bad `control_*` default, a mis-linked
libghostty - builds clean, is installed over `~/.local/bin/herdr`, then fails
line 86, and `set -e` exits 1. The owner's live multiplexer binary is now the
broken one, with no copy of the working one anywhere. That is verbatim the
outcome `research/intent.md:47-51` calls unacceptable ("it must never break my
installed herdr"), and Phase 8 has no Verify item that observes it.

**Cost of the fix: one moved line.** Smoke-test the build artifact before it
touches `$INSTALL_DIR`:

```
cargo build --release --locked
target/release/herdr --version          # gate BEFORE the destructive step
install -d "$INSTALL_DIR"
install -m 755 target/release/herdr "$INSTALL_DIR/herdr"
```

Zero added lines, zero bloat, and it converts the unacceptable outcome into a
failed build that leaves the working install untouched. The stronger form (`cp`
the existing binary to `$INSTALL_DIR/herdr.prev` before line 85) I am *not*
asking for; the reorder alone closes the stated stake.

**Verify needs the matching gate.** Phase 8's Verify block has no item asserting
"a build that produces a broken binary leaves the previous install intact". Add
one you can actually run: point the script at a scratch `INSTALL_DIR`, stub
`target/release/herdr` with `#!/bin/sh` + `exit 1`, and assert the pre-existing
file still runs afterward.

---

## MAJOR

### M1(r1) - MAJOR, VERIFIED. One interrupted first run on macOS traps every later run, permanently, with an opaque error.

**Location**: `build_and_install.sh:52-58`.

**Evidence.** The guard is `[ ! -d "$ziglib" ]`, but the work happens in
`$ziglib.tmp`, which is never cleaned and never guarded. `cp -R src dest` when
`dest` already exists as a directory copies *into* it - confirmed:
```
$ mkdir -p dest.tmp; cp -R src dest.tmp; find dest.tmp
dest.tmp/src/libcxx/include/f.h        <- nested, not the contents
```
Reproduced against the real thing (scratch `$DATA_DIR`, `.tmp` pre-created):
`cp -R "$zig_prefix/lib/zig" "$ziglib.tmp"` produced `$ziglib.tmp/zig/...`, and
the `perl -0pi -e ... "$ziglib.tmp/libcxx/include/__random/clamp_to_integral.h"`
on line 55-56 then failed on a path that does not exist.

**The interrupt window is not theoretical:**
```
$ du -sh /opt/homebrew/opt/zig@0.15/lib/zig  ->  209M
$ find /opt/homebrew/opt/zig@0.15/lib/zig -type f | wc -l  ->  18101
```
209 MB / 18,101 files. Ctrl-C, a full disk, a closed laptop, or a killed pane
during that copy all land in this state.

**Failure scenario.** A fork user on a fresh Mac hits Ctrl-C during the copy.
Every subsequent run of the script - forever - dies with
`Can't open .../zig-lib-0.15.2-patched.tmp/libcxx/include/__random/clamp_to_integral.h: No such file or directory`,
naming a path they have never heard of, in a directory nothing documents. No
message tells them to remove anything. The same trap fires on the owner's daily
driver and blocks all future rebuilds of the fork.

**Fix, one line**, before the `cp -R` at :54:
```
rm -rf "$ziglib.tmp"
```
Phase 8's "rerun idempotent" (`PLAN.md:824`) only ever observed reruns after a
*successful* run, so it cannot fail for this. Add: "rerun after `^C` during the
lib-dir copy still succeeds."

### M2(r1) - MAJOR, VERIFIED. A distro-packaged `cargo` silently disables the toolchain pin the plan's Verified facts depend on.

**Location**: `build_and_install.sh:33-39`; claim at `PLAN.md:775-776`.

**The claim**: *"`rust-toolchain.toml` pins 1.96.1, so rustup fetches the exact
toolchain on first `cargo` call; no version logic belongs in the script."*

**True only when `cargo` is rustup's shim.** The guard is `command -v cargo` - it
accepts *any* cargo on PATH, skips rustup entirely, and never prepends
`~/.cargo/bin`. `rust-toolchain.toml` is a rustup feature; a distro cargo ignores
it, so the pin the plan leans on does not exist on that machine.

**Evidence.** Debian bookworm - the first image in your own stress-test matrix
(`PLAN.md:811`) - ships:
```
$ docker run --rm debian:bookworm-slim ... apt-cache policy cargo rustc
cargo:  Candidate: 0.66.0+ds1-1
rustc:  Candidate: 1.63.0+dfsg1-2
```
`Cargo.lock` here is `version = 4`, which needs cargo >= 1.78. Reproduced end to
end in the container with `apt-get install cargo` (cargo 1.65.0 / rustc 1.63.0)
and a minimal v4 lockfile:
```
error: failed to parse lock file at: /t/Cargo.lock
Caused by:
  lock file version `4` was found, but this version of Cargo does not
  understand this lock file, perhaps Cargo needs to be updated?
```

**Failure scenario.** A fork user on debian reads "missing required tool: cc",
runs `apt install build-essential cargo` (the obvious reading), reruns. The
script passes preflight, skips rustup, downloads 50 MB of zig, and dies with a
message naming neither rustup nor herdr. On a distro with a newer but non-rustup
rust (fedora) it is worse: the lockfile parses, the build starts, and it fails
minutes later inside a dependency compiled against an unpinned rustc.

**Fix, still one condition** - gate on rustup, since the pin requires rustup:
```
if ! command -v rustup >/dev/null 2>&1 && [ ! -x "$HOME/.cargo/bin/cargo" ]; then
    echo "cargo not found; installing Rust via rustup"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
fi
export PATH="$HOME/.cargo/bin:$PATH"
```
Also correct `PLAN.md:775-776`: the pin holds *given a rustup-managed cargo*, and
the script is what has to guarantee that.

### M3(r1) - MAJOR, VERIFIED. `$SHELL` is the passwd login shell, not the shell the user uses - and the owner's own Mac is the counterexample. The gate that "verified" this was built so it cannot observe the failure.

**Location**: `build_and_install.sh:95-108`; gate at `PLAN.md:825-826`.

**Evidence, on this host, right now:**
```
$ echo $SHELL
/bin/zsh
$ ls ~/.zshrc
ls: /Users/rudrabhojbhati/.zshrc: No such file or directory
$ ls -la ~/.config/fish/config.fish
-rw-r--r-- 1 ... 1355 29 Jul 17:02 config.fish
$ fish -c 'echo $fish_user_paths'
/opt/homebrew/bin ... /Users/rudrabhojbhati/.local/bin /Users/rudrabhojbhati/.cargo/bin
$ fish --version
fish, version 4.8.1
```
The owner runs fish - populated `fish_user_paths`, a real `config.fish`, no
`.zshrc` at all - while `$SHELL` reports `/bin/zsh`. `basename "$SHELL"` -> `zsh`
-> the script would **create** a `~/.zshrc` containing an export line fish never
reads, print *"added /Users/rudrabhojbhati/.local/bin to PATH in
/Users/rudrabhojbhati/.zshrc (open a new shell)"*, and exit 0. The user opens a
new shell (fish) and nothing changed.

I also confirmed the mechanism is structural, not an accident of this machine:
bash *assigns* `SHELL` from `/etc/passwd` when it is unset, so `$SHELL` is always
the passwd login shell. In my container harness, `env -u SHELL bash script` still
took the `bash` branch - `$SHELL` was refilled as `/bin/bash`.

**Why the `[x]` did not catch it.** `PLAN.md:816-818` states the method: *"test
the PATH section in isolation ... with `$SHELL` set to each shell"*. That harness
**forces** `$SHELL`, so it validates branch dispatch and can never observe
detection failure. It is a gate that cannot fail for the bug that exists. The
`[x]` at :825-826 must not be read as covering shell detection.

**Failure scenario at your stakes.** This is the common macOS fish setup: fish
installed via brew, set as the Terminal/iTerm profile shell (or `exec fish` from
`.zshrc`), `chsh` never run, `$SHELL` still `/bin/zsh`. The script reports
success, writes a file the user's shell does not read, and `herdr` is not on
PATH. The user believes the installer did its job.

**Fix, two short options.** (a) Detect the shell that is actually configured
before trusting `$SHELL` - e.g. treat a non-empty `~/.config/fish` as the fish
signal, then fall back to `$SHELL`. (b) Keep `$SHELL` but downgrade the message
from an assertion to a verifiable instruction ("added ... to `<rc>`; if your
interactive shell is not zsh, add it there too"), and add a Verify item that
asserts *detection*, not the branch. I recommend (a) for fish specifically,
because it is the one case where the owner himself is misdetected today.

### M4(r1) - MAJOR, VERIFIED. `[x] macOS ... full run` covers one axis (the zig cache) and is worded as covering the cold machine it does not cover.

**Location**: `PLAN.md:823-824`.

The item reads: *"macOS, fresh zig caches: full run builds libghostty from
scratch (1m17s), installs, `herdr --version` ok; rerun idempotent."*

**What the instrument actually varied**: `ZIG_GLOBAL_CACHE_DIR` /
`ZIG_LOCAL_CACHE_DIR` (`PLAN.md:815-816`). Nothing else.

**What was therefore never executed on macOS**, per this host's state:
- the rustup branch (`:33-39`) - cargo is present and rustup-managed here;
- the `brew install zig@0.15` branch (`:44`) - already installed;
  `brew list --versions zig@0.15` -> `zig@0.15 0.15.2`, keg files dated
  `11 Oct 2025`, ten months before the run;
- first-time `$INSTALL_DIR` creation - `~/.local/bin` predates this by months;
- any recovery from pre-existing bad state (M1).

So the only macOS path with an `[x]` is: warm brew, warm rustup, cold zig cache.
That is a legitimate and valuable result - it is what caught your warm-cache
mirage - but the checkbox as worded is the plan's sole evidence for
`research/intent.md:47-51` ("fork users run this cold on fresh machines"), and it
cannot carry that weight. The stranger's path is the untested one.

**Fix**: reword to what was observed ("macOS with brew zig and rustup already
present, fresh zig caches: ..."), and either add the honest open item ("macOS
cold path - no rustup, no brew zig - unverified; needs a throwaway macOS user or
Tart VM per `PLAN.md:819-820`") or execute it. Do not leave an `[x]` a reader
will take as cold-machine coverage.

---

## MINOR

### m1(r1) - MINOR, VERIFIED. Linux temp extraction dirs are never cleaned; repeated failures orphan partial zig trees.
`build_and_install.sh:71-76` creates `mktemp -d "$DATA_DIR/.zig-XXXXXX"` with no
`trap`. On a mid-transfer network failure, `pipefail` correctly aborts - and
leaves however much of a ~1.3 GB extracted zig tree tar already wrote, forever,
under `~/.local/share/herdr/.zig-XXXXXX`. Each retry adds another. The official
installer does exactly this right: `website/install.sh:91-92`,
`TMP="$(mktemp -d)"` + `trap 'rm -rf "$TMP"' EXIT`. One line.

### m2(r1) - MINOR, VERIFIED. `install` is non-atomic on Linux (it is atomic on macOS).
GNU coreutils 9.1 in `debian:bookworm-slim`: installing over a running binary
succeeded and the inode changed (267011 -> 267017), so a running process is not
corrupted - good. But GNU `install` unlinks the destination before creating it,
unlike macOS's mandatory temp-file path quoted above, so `^C` or `ENOSPC` during
the 18 MB copy leaves `~/.local/bin/herdr` truncated or absent where a working
binary used to be. With B1 fixed this is a small residual; to close it too,
`install` to `$INSTALL_DIR/.herdr.new` and `mv` it into place - the `mv` is the
atomic step, one extra line, correct on both platforms.

### m3(r1) - MINOR, VERIFIED. The rc-file duplicate guard is a substring match that silently no-ops on unrelated lines.
`build_and_install.sh:109` matches the fixed string `.local/bin` anywhere in the
rc file. Any line merely *containing* it suppresses the append, and the script
then prints **nothing at all** and exits 0. Not hypothetical - the owner's own
config has exactly such a line:
```
~/.config/fish/config.fish:5: fish_add_path $HOME/.local/bin $HOME/.cargo/bin
~/.config/fish/config.fish:7: fish_add_path $HOME/.local/bin/admixtools   <- matches, adds nothing
```
A `.zshrc` with `export PATH="$HOME/.local/bin/somesdk:$PATH"` and no
`.local/bin` entry gets silently skipped. Match the exact line you write
(`-qsxF "$line"`) instead.

### m4(r1) - MINOR, VERIFIED. The macOS bash branch can shadow an existing `~/.profile`.
`build_and_install.sh:103` writes `~/.bash_profile` on macOS. On this host:
```
$ ls ~/.bash_profile   ->  No such file or directory
$ cat ~/.profile       ->  . "$HOME/.cargo/env"
```
bash login shells read the first of `~/.bash_profile`, `~/.bash_login`,
`~/.profile` that exists. Creating `~/.bash_profile` where only `~/.profile`
exists makes bash stop reading `~/.profile` entirely - here that would silently
drop `. "$HOME/.cargo/env"` from every future bash login shell. Prefer an
existing `~/.bash_profile`, else append to `~/.profile` if it exists, else create
`~/.bash_profile`. macOS-only; Linux correctly uses `~/.bashrc`.

### m5(r1) - MINOR, VERIFIED. `brew install zig@0.15` runs without `HOMEBREW_NO_AUTO_UPDATE=1`, diverging from your own CI.
`build_and_install.sh:44` vs `.github/workflows/ci.yml:111` and
`.github/workflows/release.yml:108`, both of which prefix
`HOMEBREW_NO_AUTO_UPDATE=1`. Without it, `brew install` on the daily driver runs
a full `brew update` first and will upgrade zig's outdated dependencies
(`brew cat zig@0.15`: `depends_on "lld@20"`, `"llvm@20"`, `"zstd"` - llvm@20 is a
multi-GB formula), turning "build herdr" into an unannounced multi-minute
Homebrew session mid-work. One prefix; CI already set the precedent.

### m6(r1) - MINOR, PLAUSIBLE. No `cc` / SDK preflight on macOS.
`build_and_install.sh:25` requires `brew` and `perl` but not `cc`. Homebrew's own
installer pulls in the Command Line Tools, so `need brew` transitively covers the
common case - which is why this is MINOR, not higher. But CLT can be present and
its SDK broken, and this host is in a broken-ish state today:
```
$ xcode-select -p
/Applications/Xcode-beta.app/Contents/Developer
$ xcrun --show-sdk-version
xcodebuild: error: SDK "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk" cannot be located.
```
zig resolves the macOS SDK through `xcrun`; a user in this state gets a zig error
mid-build instead of a named missing tool. Moving `need cc` out of the Linux arm
so it runs on both is one token and gives the same clear message the Linux path
already gives.

### m7(r1) - MINOR, VERIFIED. Patched lib-dir copies accumulate at 209 MB each and are never pruned.
`build_and_install.sh:51` keys on `zig version`, which is right for correctness -
but every brew zig@0.15 point release leaves the previous 209 MB copy behind in
`~/.local/share/herdr` (`du -sh ~/.local/share/herdr/zig-lib-0.15.2-patched` ->
`209M`). Not urgent at one version. Either prune `zig-lib-*-patched` entries that
are not the current one, or put an explicit "accepted, it is a cache" line in the
plan so the next reader does not think it was missed.

### m8(r1) - MINOR, VERIFIED. Alpine: the plan calls it supported, the intent record calls it a non-goal - and the Docker budget went to it while the ruled matrix stayed open.
`research/intent.md:36-38`: *"platform matrix = macOS + Linux glibc
(debian/fedora-class). Alpine/musl and Windows are non-goals."*
`PLAN.md:838-840`: *"Alpine/musl builds identically up to that point, so it is
supported given `libgcc` + `build-base`."* Those cannot both stand. The script
also has no `need libgcc`, so the attached clause - "the script's `need cc`/`need
xz` messages name the missing tools" - does not hold for the alpine case it is
attached to. Separately, the matrix at `PLAN.md:811` and `:829-836` spent a third
of its runs on a non-goal image while the ruled debian/fedora end-to-end is still
`[ ]`. Drop the alpine support claim, or take it to the owner as a scope change.

### m9(r1) - MINOR, VERIFIED. Phase 8 contributes zero entries to the decisions log; depth-parity gap vs the reference.
The reference plan's convention (its section 0 and decision register) is that
decisions carry provenance. `PLAN.md:844-879` - the decisions log - contains only
Phase 6/7 mode-design entries; nothing from Phase 8. These Phase 8 decisions
currently exist only as prose inside "Verified facts", or not at all:
- brew zig vs official tarball on macOS (excellent evidence, no log entry);
- `~/.local/share/herdr` as the toolchain home - note `research/intent.md:73-74`
  still lists this as **open** ("owner may prefer another location") while the
  script has already committed to it;
- `$SHELL` as the shell-detection signal (see M3);
- no checksum on the zig tarball, where the official installer does verify.
Add the entries, and either get the `~/.local/share/herdr` ruling or mark it
"proceeding under PROPOSAL, owner may override".

### m10(r1) - MINOR, VERIFIED. herdr's own auto-update will offer to clobber the fork build; the non-goal wording does not warn about it.
`research/intent.md:66-68` lists "updating an existing install via `herdr update`
(which would clobber the local build)" as a non-goal - phrased as "we will not
implement it". But herdr *initiates* this itself: `src/update.rs:2103`
`pub fn auto_update(...)`, `src/logging.rs:376` `update_available(version)`.
After this script installs a fork build at `~/.local/bin/herdr` - the exact path
`src/update.rs:2467` and `:2529` treat as a direct install - the running app will
offer an upstream release, and accepting it silently replaces the control-mode
patch series. That is a "breaks my installed herdr" path that arrives without the
owner running the script at all. One sentence in Phase 8 ("after installing a
fork build, do not accept in-app updates") is the whole fix.

### m11(r1) - MINOR, VERIFIED. The macOS zig source has a dated expiry that Verified facts does not mention.
`brew cat zig@0.15`:
```
deprecate! date: "2027-04-15", because: :unsupported
disable!   date: "2028-04-15", because: :unsupported
```
After 2028-04-15 `brew install zig@0.15` fails outright and the macOS path stops
working for every fork user. `PLAN.md:789-791` already names the removal
condition for the INFINITY patch (zig 0.16, herdrdev/herdr#285); this is the same
class of fact and belongs next to it, because it puts a hard date on the whole
macOS branch, not just the workaround.

---

## NITs (one list, no round spent)

- `build_and_install.sh:98`: `$INSTALL_DIR` is single-quote-interpolated into a
  `fish -c` string; a `$HOME` containing an apostrophe breaks the quoting.
- `build_and_install.sh:14`: `cd "$(dirname "$0")"` resolves the symlink's
  directory, not the repo, if the script is invoked through a symlink.
- `build_and_install.sh:76`: `rmdir "$tmp"` fails (and aborts under `set -e`) if
  the tarball ever grows a second top-level entry. `rm -rf` cannot fail that way,
  and it becomes moot with m1's `trap`.
- The zig tarball is fetched without a checksum while `website/install.sh:98-105`
  verifies SHA-256 for the herdr binary. TLS plus `tar -J`'s own integrity check
  covers the realistic corruption cases, so I am not asking for it - noting the
  asymmetry only so it is a decision rather than an oversight.

---

## A harness that closes most of the Linux gap without raising Docker memory

`PLAN.md:837-840` leaves Linux end-to-end blocked on a user setting (Docker
Desktop >= 4 GB). That blocks the *compile*, not the rest of the script - and
"the rest" is where the install and PATH logic live, none of which has ever
executed on Linux. You can exercise all of it inside the existing 2 GB cap by
stubbing cargo. I ran this; it works:

```sh
# /stub/cargo, first on PATH
#!/bin/sh
"$ZIG" version >/dev/null || { echo "STUB: ZIG wrapper unusable"; exit 1; }
mkdir -p target/release
printf '#!/bin/sh\necho "herdr 0.8.0"\n' > target/release/herdr
chmod +x target/release/herdr
```

Six runs in `debian:bookworm-slim` (real zig download, real extraction, real
install, real rc-file edits): `SHELL=/bin/bash` -> appends to `~/.bashrc` once;
rerun -> exactly one `.local/bin` line in `~/.bashrc`; `SHELL=/usr/bin/zsh` ->
creates `~/.zshrc`; `SHELL=/usr/bin/fish` -> `fish_user_paths` =
`/root/.local/bin`; already-on-PATH -> silent exit 0; no leftovers in
`~/.local/share/herdr` beyond `zig-aarch64-linux-0.15.2`. **All of that passed** -
the Linux non-compile path is in better shape than the plan can currently claim,
and this harness is how you get to claim it. It is also the harness that would
catch B1 (stub a `target/release/herdr` that exits 1, assert the previous install
survives) and M1 (pre-create `$ziglib.tmp`).

---

## Summary and what I need back

**BLOCKER**: B1 - smoke test after the overwrite.
**MAJOR**: M1 (`.tmp` trap), M2 (distro cargo defeats the pin), M3 (`$SHELL`
misdetects the owner's own shell; the gate cannot fail), M4 (`[x]` overstates the
macOS coverage).
**MINOR**: m1-m11. **NIT**: four, no round.

The macOS technical core - brew zig over the tarball, the INFINITY patch, the
private lib-dir copy, the wrapper - is right, and I verified it rather than
taking your word. What is weak is everything around the *edges* of a successful
run: what happens after an interruption, on a machine whose rust came from
somewhere else, for a user whose shell is not their `$SHELL`, and the ordering of
the one destructive step against the one gate that guards it.

For the reply, give me the exact diff (or final text) for the
`build_and_install.sh` changes and for each edited `PLAN.md` line, not a summary
of intent. I re-read both files and re-run the checks; a claimed fix that is not
in the file will come back in round 2.
