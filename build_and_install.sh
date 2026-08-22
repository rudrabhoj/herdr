#!/usr/bin/env bash
# Build herdr from this checkout and install it to ~/.local/bin.
#
# - Installs Rust via rustup if rustup is missing (rust-toolchain.toml pins the
#   exact toolchain; rustup honors it on first use - a distro cargo would not).
# - Zig 0.15 for the vendored libghostty-vt (build.rs shells out to $ZIG).
#   macOS uses Homebrew's zig@0.15: it backports the MachO linker fix for
#   Xcode 26.4+ SDKs (libSystem.tbd only lists arm64e now), which the official
#   0.15.2 tarball lacks, so the tarball cannot link on current macOS. Linux
#   fetches the official tarball into ~/.local/share/herdr.
# - Adds ~/.local/bin to PATH in your shell's config if it is not there yet.
set -euo pipefail

cd "$(dirname "$0")"

ZIG_VERSION=0.15.2
INSTALL_DIR="$HOME/.local/bin"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/herdr"

need() {
    command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1" >&2; exit 1; }
}

case "$(uname -s)" in
    Darwin) os=macos; need brew; need perl ;;
    Linux) os=linux; need xz ;;  # xz unpacks the zig tarball
    *) echo "unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac
need cc  # links the Rust crates
need curl
need tar

# --- rust ---------------------------------------------------------------------
# Gate on rustup, not cargo: only a rustup-managed cargo honors the toolchain pin.
if ! command -v rustup >/dev/null 2>&1 && [ ! -x "$HOME/.cargo/bin/cargo" ]; then
    echo "rustup not found; installing Rust via rustup"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
fi
export PATH="$HOME/.cargo/bin:$PATH"

# --- zig ----------------------------------------------------------------------
mkdir -p "$DATA_DIR"
if [ "$os" = macos ]; then
    brew list zig@0.15 >/dev/null 2>&1 || HOMEBREW_NO_AUTO_UPDATE=1 brew install zig@0.15
    zig_prefix="$(brew --prefix zig@0.15)"
    zig_ver="$("$zig_prefix/bin/zig" version)"
    # The macOS 26 SDK no longer exposes INFINITY to zig 0.15's bundled libcxx,
    # which breaks the vendored build. Patch a private copy of the lib dir
    # (never the brew keg) and point a wrapper at it; goes away when upstream
    # moves to zig 0.16 (herdrdev/herdr#285).
    ziglib="$DATA_DIR/zig-lib-$zig_ver-patched"
    if [ ! -d "$ziglib" ]; then
        echo "creating patched copy of zig $zig_ver lib dir at $ziglib"
        rm -rf "$ziglib.tmp"
        cp -R "$zig_prefix/lib/zig" "$ziglib.tmp"
        perl -0pi -e 's/_LIBCPP_BEGIN_NAMESPACE_STD/#ifndef INFINITY\n#  define INFINITY __builtin_inff()\n#endif\n\n_LIBCPP_BEGIN_NAMESPACE_STD/' \
            "$ziglib.tmp/libcxx/include/__random/clamp_to_integral.h"
        mv "$ziglib.tmp" "$ziglib"
    fi
    zig="$DATA_DIR/zig"
    printf '#!/bin/sh\nexec "%s" "$@" --zig-lib-dir "%s"\n' "$zig_prefix/bin/zig" "$ziglib" > "$zig"
    chmod +x "$zig"
else
    case "$(uname -m)" in
        aarch64 | arm64) arch=aarch64 ;;
        x86_64 | amd64) arch=x86_64 ;;
        *) echo "unsupported arch: $(uname -m)" >&2; exit 1 ;;
    esac
    zig_dir="$DATA_DIR/zig-$arch-linux-$ZIG_VERSION"
    if [ ! -x "$zig_dir/zig" ]; then
        echo "fetching zig $ZIG_VERSION into $DATA_DIR"
        tmp="$(mktemp -d "$DATA_DIR/.zig-XXXXXX")"
        trap 'rm -rf "$tmp"' EXIT
        curl --proto '=https' --tlsv1.2 -sSfL \
            "https://ziglang.org/download/$ZIG_VERSION/zig-$arch-linux-$ZIG_VERSION.tar.xz" \
            | tar -xJ -C "$tmp"
        mv "$tmp/zig-$arch-linux-$ZIG_VERSION" "$zig_dir"
    fi
    zig="$zig_dir/zig"
fi
export ZIG="$zig"

# --- build + install ----------------------------------------------------------
cargo build --release --locked
# Smoke-test the artifact before it touches the live install; then replace
# atomically so an interrupted copy cannot leave a truncated binary.
target/release/herdr --version
install -d "$INSTALL_DIR"
install -m 755 target/release/herdr "$INSTALL_DIR/.herdr.new"
mv "$INSTALL_DIR/.herdr.new" "$INSTALL_DIR/herdr"
echo "installed to $INSTALL_DIR/herdr"

# --- config -------------------------------------------------------------------
# Render herdr.config.toml (the fork's template) into herdr's config path. Only
# config.toml is written: session.json, logs, sockets, release notes, plugin
# locks, and agent-detection overrides are per-machine private state and are
# never read or copied. default_shell gets an absolute path resolved on THIS
# machine (fish when installed - the template is tuned for it - else empty,
# which makes herdr use $SHELL), so a brew-only or distro-only path never
# travels between machines. Same precedence as herdr: HERDR_CONFIG_PATH, then
# XDG_CONFIG_HOME, then ~/.config.
cfg="${HERDR_CONFIG_PATH:-${XDG_CONFIG_HOME:-$HOME/.config}/herdr/config.toml}"
shell="$(command -v fish 2>/dev/null || true)"
[ -x "$shell" ] || { shell=""; echo "fish not found; default_shell left empty so herdr uses \$SHELL"; }
install -d "$(dirname "$cfg")"
new="$(dirname "$cfg")/.config.toml.new"
# Pure-bash substitution: no sed/awk escaping rules for the path to trip over.
while IFS= read -r line || [ -n "$line" ]; do
    printf '%s\n' "${line//@DEFAULT_SHELL@/$shell}"
done < herdr.config.toml > "$new"
# Validate the rendered file with the binary that will read it before it can
# replace a working config.
if ! HERDR_CONFIG_PATH="$new" "$INSTALL_DIR/herdr" config check; then
    rm -f "$new"
    echo "herdr.config.toml renders to an invalid config; existing config left untouched" >&2
    exit 1
fi
if cmp -s "$new" "$cfg"; then
    rm -f "$new"
    echo "config unchanged at $cfg"
else
    [ ! -f "$cfg" ] || { cp -p "$cfg" "$cfg.bak"; echo "previous config saved to $cfg.bak"; }
    mv "$new" "$cfg"
    echo "installed config to $cfg"
    # A running server keeps its old config until told; best effort, no server is fine.
    "$INSTALL_DIR/herdr" server reload-config >/dev/null 2>&1 || true
fi
# Popup commands in the template are resolved at use time, not here; say so now
# instead of failing silently inside a popup later.
grep -E '^command = "' herdr.config.toml | cut -d'"' -f2 | while read -r popup; do
    command -v "${popup%% *}" >/dev/null 2>&1 \
        || echo "note: $popup is not installed; its [[keys.command]] popup will fail until it is"
done

# --- PATH ---------------------------------------------------------------------
case ":$PATH:" in
    *":$INSTALL_DIR:"*) exit 0 ;;
esac

# $SHELL is the passwd login shell, which often stays zsh/bash while the user
# actually runs fish - and a ~/.config/fish dir survives a single `fish` run -
# so add to fish when its config exists AND still edit the $SHELL rc. Over-adding
# is cheap; a missing entry is the failure.
if [ -d "${XDG_CONFIG_HOME:-$HOME/.config}/fish" ] && command -v fish >/dev/null 2>&1; then
    # fish_add_path exits 1 when nothing was added, so guard for reruns.
    fish -c "contains -- '$INSTALL_DIR' \$fish_user_paths; or fish_add_path -U '$INSTALL_DIR'"
    echo "$INSTALL_DIR is in fish_user_paths"
fi
line='export PATH="$HOME/.local/bin:$PATH"'
case "$(basename "${SHELL:-}")" in
    fish) exit 0 ;;
    zsh) rc="$HOME/.zshrc" ;;
    bash)
        rc="$HOME/.bashrc"
        if [ "$os" = macos ]; then
            # Login shells read only the first of .bash_profile/.bash_login/.profile;
            # creating .bash_profile next to an existing .profile would shadow it.
            rc="$HOME/.bash_profile"
            [ -f "$rc" ] || [ ! -f "$HOME/.profile" ] || rc="$HOME/.profile"
        fi
        ;;
    *)
        echo "add $INSTALL_DIR to your PATH, e.g.: $line"
        exit 0
        ;;
esac
if ! grep -qsxF "$line" "$rc"; then
    printf '\n%s\n' "$line" >> "$rc"
    echo "added $INSTALL_DIR to PATH in $rc (open a new shell)"
fi
