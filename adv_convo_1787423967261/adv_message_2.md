# adv_message_2 - round 2

Reviewed the committed state, not the reply: `cc2207b8 build: harden
build_and_install.sh per adversarial round 1`, working tree clean for
`build_and_install.sh`, `PLAN.md`, `research/intent.md`. I re-ran every fix I
could rather than reading the diff for it.

## Round-1 dispositions, re-verified

| id | claim | my check | verdict |
|----|-------|----------|---------|
| B1 | smoke test before install, `.herdr.new` + `mv` | debian, stub `~/.cargo/bin/cargo` emitting an artifact that `exit 1`s, over a pre-existing `~/.local/bin/herdr` printing `OLD-GOOD` | **CLOSED.** `rc=1`; `~/.local/bin/herdr` still prints `OLD-GOOD`; `ls -la ~/.local/bin/` shows one file, no `.herdr.new` |
| M1 | `rm -rf "$ziglib.tmp"` before `cp -R` | scratch `DATA_DIR`, pre-created `zig-lib-0.15.2-patched.tmp/junk/x`, ran the real :52-59 block against the real brew keg | **CLOSED.** rc=0; `define INFINITY` present once in the patched header; no `.tmp` left |
| M2 | gate on `rustup`, always prepend `~/.cargo/bin` | read `:35-39`; the stub harness relies on the unconditional prepend and picks it up | **CLOSED.** The pin now cannot be silently bypassed by a distro cargo; `PLAN.md:776-781` states the conditionality correctly |
| M3 | detect fish before `$SHELL` | debian, `$SHELL=/usr/bin/zsh` + `~/.config/fish` | **the owner's case is fixed - but the fix has an inverse failure. See M5 below.** |
| M4 | `[x]` reworded, cold-macOS open item added | `PLAN.md:856-858`, `:881-882` | **CLOSED.** "This is NOT cold-machine coverage" plus a `[ ]` open item is exactly right |
| m1 | `trap 'rm -rf "$tmp"' EXIT` | debian, two full runs | **CLOSED.** `~/.local/share/herdr` holds only `zig-aarch64-linux-0.15.2` |
| m2 | atomic replace | folded into B1's `mv`; same-directory rename | **CLOSED** |
| m3 | `grep -qsxF "$line"` | `.bashrc` seeded with `export PATH="$HOME/.local/bin/other:$PATH"` | **CLOSED.** line appended despite the near-miss; rerun leaves exactly 1 |
| m4 | macOS bash rc selection | ran the `[ -f "$rc" ] \|\| [ ! -f .profile ] \|\| rc=.profile` chain over all four states | **CLOSED.** `no/no -> .bash_profile`, `no/yes -> .profile`, `yes/yes -> .bash_profile`, `yes/no -> .bash_profile`. Correct, and no `set -e` hazard |
| m5 | `HOMEBREW_NO_AUTO_UPDATE=1` | `:44` | **CLOSED** |
| m6 | `need cc` on both | `:29` | **moved, but it asserts nothing on macOS. See m12** |
| m7 | cache accepted | `PLAN.md:800-801` | **CLOSED**, stated with the manual-delete note |
| m8 | Alpine non-goal | `PLAN.md:879-880`, strategy list at `:839` | **CLOSED** |
| m9 | decisions log entry | `PLAN.md:919-928`; `research/intent.md:74-75` | **CLOSED.** Carries brew-vs-tarball, DATA_DIR-under-PROPOSAL, shell detection, smoke-before-install, and the no-checksum decision |
| m10 | in-app updater warning | `PLAN.md:818-821` | **CLOSED** |
| m11 | brew deprecate/disable dates | `PLAN.md:792-794` | **CLOSED** |
| NITs | 3 removed with the trap; 1, 2, 4 dispositioned | - | accepted |

Also independently reproduced the new `[x]` at `PLAN.md:873-876` (Linux
stub-cargo harness): real zig fetch, install, atomic replace, `~/.bashrc` gains
exactly one line, second run a no-op, exit 0 both. That checkbox is honest.

---

## MAJOR

### M5(r2) - MAJOR, VERIFIED. The fish fix inverts the failure: any user who has ever run `fish` once now gets the fish branch, and their real shell's rc is never touched.

**Location**: `build_and_install.sh:100-112`; gate at `PLAN.md:865-866`.

```
100  if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
101      shell=fish
...
107      fish)
109          fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
110          echo "$INSTALL_DIR is in fish_user_paths"
111          exit 0
```

The predicate is "a fish config dir exists", and the branch `exit 0`s. Neither
half is safe.

**Evidence 1 - one invocation of fish is enough to create the dir.** Clean
`debian:bookworm-slim`, fish installed but never configured:
```
(absent before)
$ fish -c 'echo hi'
A: RUNNING FISH ONCE CREATED ~/.config/fish
```
So `~/.config/fish` is not evidence that fish is the user's shell. It is evidence
that fish has been *executed*, once, ever - by the user trying it, by a dotfiles
checkout, or by a script.

**Evidence 2 - the resulting failure, reproduced.** Same container,
`$SHELL=/usr/bin/zsh` (a genuine zsh user), `~/.config/fish` present from that
single `fish -c`, no `.zshrc`:
```
installed to /root/.local/bin/herdr
/root/.local/bin is in fish_user_paths
rc=0
B: NO .zshrc  <-- zsh user got nothing
-- fish_user_paths --
/root/.local/bin
```
The script exits 0, prints a success line, leaves `~/.zshrc` untouched, and
**writes a universal variable into the `fish_variables` of a shell the user does
not use**. The zsh user opens a new shell and `herdr` is not on PATH.

That is the identical failure M3 named - "the script reports success, writes a
file the user's shell does not read" - now pointing the other way. Swapping which
population gets it wrong is not a fix; the one-sided predicate cannot win.

**Why the new `[x]` did not catch it.** `PLAN.md:865-866` tests exactly one
direction: *"`$SHELL=/bin/zsh` with a `~/.config/fish` dir takes the fish branch
and writes `fish_user_paths`, no `.zshrc` created"*. That is the fix's own success
criterion restated - the observation "no `.zshrc` created" is recorded as the
*pass* condition for the case where it is the *bug*. The gate was written to
confirm the change, not to try to break it. It cannot fail.

**Fix: stop choosing, do both, and drop the `exit 0`.** Roughly line-neutral:

```sh
# $SHELL is the passwd login shell, which often stays zsh/bash while the user
# actually runs fish - and a ~/.config/fish dir survives a single `fish` run,
# so handle fish when its config exists AND still edit the $SHELL rc.
if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
    # fish_add_path exits 1 when nothing was added, so guard for reruns.
    fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
    echo "$INSTALL_DIR is in fish_user_paths"
fi
line='export PATH="$HOME/.local/bin:$PATH"'
case "$(basename "${SHELL:-}")" in
    fish) exit 0 ;;
    zsh)  rc="$HOME/.zshrc" ;;
    bash) ... unchanged ...
    *)    echo "add $INSTALL_DIR to your PATH, e.g.: $line"; exit 0 ;;
esac
```

This deletes the `shell=` selection block and turns the `fish)` arm into a bare
`exit 0`, so it is not net-new code. The asymmetry is deliberate and worth
stating in the plan: **over-adding is cheap, under-adding is the failure.** A
duplicate PATH entry or a `~/.zshrc` the owner never opens costs nothing; a
missing entry is the bug. On the owner's own Mac this writes `fish_user_paths`
(already correct, so a no-op) and creates a `~/.zshrc` he does not have - accept
that, or note it as the known cosmetic cost.

**And replace the gate with one that can fail.** `PLAN.md:865-866` should assert
the *inverse*: "a `$SHELL=zsh` user with a `~/.config/fish` dir gets BOTH
`fish_user_paths` and a `~/.zshrc` line", plus the existing fish-user direction.
Two cases, both runnable in the debian harness you already adopted.

---

## MINOR

### m12(r2) - MINOR, VERIFIED. `need cc` on macOS asserts nothing, and `PLAN.md:805-806` now states the opposite as a verified fact.

**Location**: `build_and_install.sh:29`; claim at `PLAN.md:805-806`.

The plan now says: *"`need cc` runs on both platforms (macOS CLT can be absent or
its SDK broken, as `xcrun --show-sdk-version` is on this host today)."* The first
clause is true; the parenthetical does not follow from it. `command -v cc`
succeeds on a Mac with **no** Command Line Tools, because `/usr/bin/cc` is not a
compiler - it is one of the `xcode-select` shim links that ship in base macOS:
```
$ ls -l /usr/bin/cc /usr/bin/clang /usr/bin/git
-rwxr-xr-x  78 root wheel  118928 25 Jun 07:59 /usr/bin/cc
-rwxr-xr-x  78 root wheel  118928 25 Jun 07:59 /usr/bin/clang
-rwxr-xr-x  78 root wheel  118928 25 Jun 07:59 /usr/bin/git
$ pkgutil --file-info /usr/bin/cc
volume: /
path: /usr/bin/cc          <- no pkgid: not owned by any installed package
```
78 hard links to a single 118 KB stub, `cc`/`clang`/`git` byte-identical. That
stub exists before any developer tools are installed; running it prints
"xcode-select: note: No developer tools were found". So the macOS half of the
preflight is a gate that cannot fail for the condition it names.

**Why MINOR and not MAJOR**: `need brew` (`:25`) transitively covers the realistic
case, since Homebrew's installer requires and installs the CLT. The consequence of
the hole is a confusing mid-build error on an unusual machine, not a wrong
outcome - which is why I ranked it MINOR in round 1 and rank it MINOR now.

**What has to change** is the plan sentence, which currently claims coverage the
script does not have. Either delete the parenthetical at `PLAN.md:805-806` and say
plainly that macOS CLT coverage rides on `need brew`, or make the check observe
its subject on macOS, e.g. `xcrun -f cc >/dev/null 2>&1 ||` with a message naming
`xcode-select --install`. Both are one line. I have no preference; what I object
to is an unbacked "verified fact".

---

## NITs (one list, no round spent)

- An interrupt between `:89` and `:90` leaves an 18 MB `~/.local/bin/.herdr.new`.
  It is a dotfile, so it cannot shadow `herdr`, and the next run overwrites it.
  Noting it only so it is a known artifact.
- The stub-cargo harness (`PLAN.md:873-876`) ran on `debian:bookworm-slim` only.
  `fedora:latest` is the other ruled distro and the harness is nearly free there;
  it would also cover a different coreutils `install` and a different default
  `$SHELL`. Cheap, low yield - your call.
- `research/intent.md:71-73` still frames the Docker memory question as open. It
  is now much less load-bearing, since the stub harness covers everything the
  2 GB cap blocked except the compile itself. Worth downgrading the wording.

---

## Status

**BLOCKER**: none.
**MAJOR**: M5 - the fish predicate, and the gate written to confirm it.
**MINOR**: m12. **NIT**: three.

Round-1 work is genuinely done: B1, M1, M2, M4 and every MINOR are closed by my
own re-runs, not by your description of them, and the new Verify items other than
the detection one are honest. M5 is the only thing standing between this and
convergence, and it is a shape change to ~6 lines, not new machinery.

Send the diff for `build_and_install.sh:98-112` and the replacement text for
`PLAN.md:805-806` and `PLAN.md:865-870`. I will re-run both directions of the
shell-detection case in the debian harness before I call it.
