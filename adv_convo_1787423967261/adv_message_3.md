# adv_message_3 - round 3

Reviewed the committed state: `c9cc4d16 build: adversarial round 2 - add fish and
shell rc both, plan fixes`, tree clean for the three files. `bash -n` OK.

## Round-2 dispositions, re-verified

**M5 - CLOSED.** Re-ran all three directions in `debian:bookworm-slim` against the
committed script, with a stub `~/.cargo/bin/cargo`:

```
A: zsh user WITH leftover fish dir (fish -c true once)
   rc=0   .zshrc: 1   fish_user_paths: /root/.local/bin
   rerun: .zshrc: 1   fish_user_paths: /root/.local/bin      <- idempotent, both
B: genuine fish user (SHELL=fish)
   rc=0   .zshrc: ABSENT   .bashrc: ABSENT   fish_user_paths: /root/.local/bin
C: zsh user, no fish dir
   rc=0   .zshrc: 1   fish_user_paths: (empty)
```
Both directions land, neither over-fires, reruns are clean. The `[x]` at
`PLAN.md:875-882` now describes a gate that can fail, and it passes.

**m12 - CLOSED.** `PLAN.md:805-810` no longer claims macOS coverage it does not
have; it names the shim, points CLT coverage at `need brew`, and marks the broken
SDK case accepted. Leaving the script alone is the right call - I asked for the
claim to match the artifact, not for an `xcrun` gate, and your reason for not
adding one (this host's `xcrun --show-sdk-version` is broken while zig builds
fine) is sound and is exactly why an `xcrun` gate would have been a false
negative.

**Your fedora `[x]` (`PLAN.md:886-888`) - reproduced, not taken on trust.**
`fedora:latest`, `dnf install fish zsh gcc xz curl tar`, `fish -c true` once,
`$SHELL=/usr/bin/zsh`, full script twice:
```
rc=0 / rc=0
zshrc lines: 1
fish_user_paths: /root/.local/bin
DATA_DIR: zig-aarch64-linux-0.15.2      <- no .zig-* leftovers
~/.local/bin/herdr -> herdr             <- installed artifact runs
```
Matches your text exactly.

**NITs 1-3 - dispositioned as claimed** (`.herdr.new` artifact noted in the
Implement step; fedora harness recorded; `research/intent.md:71-74` downgraded).

---

## MAJOR

### M6(r3) - MAJOR, VERIFIED. The fish check hardcodes `$HOME/.config/fish`, so a fish user with a custom `XDG_CONFIG_HOME` gets nothing at all - silently, exit 0.

**Location**: `build_and_install.sh:102`.

```
102  if [ -d "$HOME/.config/fish" ] && command -v fish >/dev/null 2>&1; then
...
108  case "$(basename "${SHELL:-}")" in
109      fish) exit 0 ;;
```

fish honors `XDG_CONFIG_HOME` and puts its config in `$XDG_CONFIG_HOME/fish`.
When that is set to anything but the default, line 102 is false, the fish block
is skipped, `$SHELL` is fish, and line 109 exits 0 - so the fish arm runs no
`fish_add_path`, no rc file is touched, and the `*)` hint that would otherwise
print is never reached. The script's last words are "installed to
~/.local/bin/herdr" and it returns success.

**Evidence**, committed script, `debian:bookworm-slim`:
```
$ export XDG_CONFIG_HOME=~/.dotcfg; fish -c true
fish config landed at: /root/.dotcfg/fish
ls: cannot access '/root/.config/fish': No such file or directory

$ SHELL=/usr/bin/fish bash /work/build_and_install.sh
herdr
installed to /root/.local/bin/herdr
rc=0

.zshrc: ABSENT   .bashrc: ABSENT
fish_user_paths=[]          <- the fish user got nothing
```

**Why this is the same class, not a new one.** It is the third instance of "the
script decides where the user's shell config lives and is wrong": M3 (passwd
`$SHELL`), M5 (fish-dir-implies-fish-user), and now the config *location*. The
outcome is identical each time - exit 0, a success message, PATH not set. Cost to
a stranger: they run herdr, get `command not found`, and have nothing in the
output to go on.

**The script already knows better.** Line 18 does exactly the right thing for the
sibling variable:
```
18  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/herdr"
```
Line 102 should mirror it. **One token, no added lines:**
```sh
if [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/fish" ] && command -v fish >/dev/null 2>&1; then
```
With that, case D above takes the fish block, `fish_user_paths` gets set, and
`fish) exit 0` is correct rather than silent. I am not asking for anything beyond
the substitution - the `fish)` arm does not need a fallback once the predicate
can actually see the config.

**Probability, stated honestly**: smaller than M3's or M5's. `XDG_CONFIG_HOME` is
set by a minority of dotfiles users, not by default anywhere. I am ranking this
MAJOR on consequence per the rubric - a silent no-op that leaves the script's
stated job undone - not on how many people hit it. It is a one-round fix.

**And one Verify line.** `PLAN.md:875-882` enumerates the shell cases but assumes
the default config location throughout. Add the fourth case to the same debian
harness: "a `$SHELL=fish` user with `XDG_CONFIG_HOME` set elsewhere still gets
`fish_user_paths`". Without it, the gate keeps testing only the layout the code
assumes.

---

## NIT (one line, no round)

- `build_and_install.sh:104`: if `fish -c` fails (a read-only `fish_variables`,
  fish older than 3.2 with no `fish_add_path`), `set -e` aborts before the
  `$SHELL` rc is edited, so a failure in the *secondary* shell blocks the
  *primary* one. Pre-existing behavior, unchanged by round 2, and I would not add
  error handling for it - noting it only so the ordering is deliberate.

---

## Status

**BLOCKER**: none. **MAJOR**: M6 only. **MINOR**: none open. **NIT**: one.

Everything from rounds 1 and 2 is closed by my own re-runs. M6 is a single token
on line 102 plus one Verify case. Send that diff and the `PLAN.md:875-882`
replacement; I will re-run the four shell-detection cases, including the
`XDG_CONFIG_HOME` one, and if they pass I expect to converge in the next message.
