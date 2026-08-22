# adv_message_4 - round 4

Reviewed `7ce3de02 build: adversarial round 3 - honor XDG_CONFIG_HOME for the
fish check`, tree clean for the three files.

## M6 - CLOSED, re-verified

`build_and_install.sh:102` now reads
`if [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/fish" ] && command -v fish ...`;
no hardcoded `$HOME/.config/fish` remains outside the comment; `bash -n` OK.
All four shell-detection cases re-run against the committed script in
`debian:bookworm-slim`:

```
A  zsh user + leftover fish dir   rc=0  .zshrc: 1        fish_user_paths: /root/.local/bin
   rerun                                 .zshrc: 1        fish_user_paths: /root/.local/bin
B  SHELL=fish, default XDG        rc=0  .zshrc: ABSENT   fish_user_paths: /root/.local/bin
C  zsh user, no fish dir          rc=0  .zshrc: 1        fish_user_paths: (empty)
D  SHELL=fish, XDG_CONFIG_HOME=~/.dotcfg
                                  rc=0  .zshrc: ABSENT   fish_user_paths: /root/.local/bin
```
D was the finding; it is now the same as B, and A/B/C did not regress.

I also confirmed by diff that **nothing outside the PATH section changed since
`cc2207b8`**, so my earlier verifications still cover the current file - and I
re-ran the BLOCKER gate against the final script anyway:
```
stub cargo emits a target/release/herdr that exits 1, over a live OLD-GOOD install
rc=1
~/.local/bin/herdr -> OLD-GOOD          <- live install survived
~/.local/bin contains one file          <- no .herdr.new orphan
~/.local/share/herdr -> zig-... only    <- no .zig-* leftovers
```

No BLOCKER, no MAJOR, no MINOR open. One NIT stands, accepted and documented.

---

CONVERGED - no remaining blocking finding.

Rounds 1-3 closed one BLOCKER (B1), six MAJORs (M1-M6) and eleven MINORs, every
one re-verified by me against the committed tree rather than the reply. The two
claims the macOS design rests on - the tarball's `-lSystem` failure on Xcode
26.4+ SDKs and the INFINITY/libcxx break - I reproduced independently in round 1
and they hold. The owner's stated unacceptable outcome is now structurally
prevented: the build artifact is smoke-tested before the live install is touched,
and the replacement is a same-directory `mv`.

## Residual risks I accept

Ordered by what they could cost.

1. **The macOS cold path has never been executed** (`PLAN.md` open item). No
   machine has run this with rustup absent AND brew zig absent AND
   `~/.local/bin` absent. Every macOS `[x]` was measured on a host where brew
   zig has been installed since Oct 2025 and rustup was already present. The
   individual pieces are sound - `brew install zig@0.15` is what CI does,
   `rustup ... --no-modify-path` is standard - but the composition is untested
   and this is the exact path a stranger takes. Highest residual.
2. **The Linux end-to-end compile has never completed anywhere on this host.**
   The stub-cargo harness covers preflight, rustup gating, zig fetch/extract/mv,
   install, atomic replace and all PATH branches on debian and fedora - that is
   real coverage and I reproduced it - but the final `rustc` of the herdr crate
   is still only known to be SIGKILLed under the 2 GB cap. Upstream CI compiles
   herdr on Linux, so the risk is a fork-specific compile problem, not a script
   problem.
3. **`need cc` asserts nothing on macOS**; CLT coverage rides on `need brew`.
   Documented at `PLAN.md:805-810`. A machine with brew but broken developer
   tools gets a zig error mid-build instead of a named missing tool.
4. **A dated expiry on the macOS branch**: `brew` marks `zig@0.15`
   `deprecate! 2027-04-15` / `disable! 2028-04-15`. After the second date the
   macOS path stops working unless herdr has moved to zig 0.16
   (herdrdev/herdr#285). Recorded; nothing to do now.
5. **No checksum on the zig tarball**, against the official installer's
   SHA-256 verification of its own binary. A recorded decision, not an
   oversight, and TLS plus `tar -J`'s integrity check covers the realistic
   corruption cases.
6. **209 MB per zig version accumulates** in `~/.local/share/herdr`, pruned by
   hand. Accepted as a cache.
7. **`fish -c` failure aborts before the `$SHELL` rc edit** (NIT), and an
   interrupt between `install` and `mv` leaves a `.herdr.new` dotfile. Both
   documented, neither worth code.
8. **The PATH-membership test is a literal substring match**, so a PATH
   containing the directory under a different spelling (trailing slash,
   symlinked home) causes a duplicate entry to be added rather than a skip.
   Harmless under the "over-adding is cheap" doctrine now stated in the plan.
9. **herdr's own in-app updater will still offer upstream releases** over a fork
   build and clobber the control-mode patch series. Documented at
   `PLAN.md:818-821`; it is a human-discipline item, not a script one.
10. **I verified that replacing a running binary leaves the running process
    intact using `/bin/sleep`, not `herdr` itself.** The mechanism is the inode,
    so it generalizes, but no test in this loop had a real herdr server running
    from the target path. The `mv`-based replace makes this safe by
    construction; I note it so nobody reads the checkbox as stronger than it is.
11. **`~/.local/share/herdr` is still a PROPOSAL**, not an owner ruling
    (`research/intent.md:74-75`). The script has committed to it.
12. **Invoking the script through a symlink** resolves the symlink's directory,
    not the repo (NIT, unfixed by choice).

## Execution order I accept for Phase 8's open items

1. **macOS cold path** (`PLAN.md` open item) - a throwaway macOS user via
   `sysadminctl -addUser`, or a Tart VM. Do this before pointing any fork user
   at the script; it is the only residual that costs a stranger real time, and
   it is the one the plan's stakes sentence is actually about.
2. **Linux end-to-end compile** (debian + fedora) once Docker Desktop memory is
   raised to >= 4 GB. Lower priority than 1: the stub harness already covers
   everything except rustc's peak RSS, and upstream CI compiles herdr on Linux
   every run.
3. **The `~/.local/share/herdr` ruling** - a one-line answer from the owner that
   turns residual 11 from a PROPOSAL into a decision.
4. Items 3-12 above need no work; they are recorded where a future reader will
   meet them.

Nothing in this list blocks running the script on the owner's Mac today. That
was the question the loop existed to answer, and the answer is yes.
