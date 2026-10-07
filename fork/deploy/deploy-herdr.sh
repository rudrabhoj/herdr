#!/usr/bin/env bash
# Upgrade the live herdr to a staged fork build without losing agent sessions.
# PLAN.md Phases 11-12 (hardened). Usage:
#   NEW_BIN=<staged herdr> deploy-herdr.sh dry-run   # nothing stops, nothing changes live
#   NEW_BIN=<staged herdr> deploy-herdr.sh deploy    # run detached: setsid -f ... </dev/null
#   deploy-herdr.sh rollback [run dir]               # back to the old release by hand
# Every root is a variable (live defaults) so a rehearsal can point all of them
# at an isolated copy. No path is derived from inherited HERDR_* variables.
set -euo pipefail

BIN_DIR=${BIN_DIR:-$HOME/.local/bin}
VW_BASE=${VW_BASE:-$HOME/.local/share/void-workstation}
HERDR_CFG=${HERDR_CFG:-$HOME/.config/herdr}
WORK=${WORK:-$HOME/.local/share/claude-accounts}
CODEX_HOME_DIR=${CODEX_HOME_DIR:-$HOME/.codex}
PI_AGENT_DIR=${PI_AGENT_DIR:-$HOME/.pi/agent}
FISH_COMPLETIONS=${FISH_COMPLETIONS:-$HOME/.config/fish/completions/herdr.fish}
TEMPLATE=${TEMPLATE:-$HOME/Dev/herdr_and_claude/herdr/herdr.config.toml}
REVIEW_DIR=${REVIEW_DIR:-$HOME/Dev/herdr_and_claude/herdr}
NEW_REL=${NEW_REL:-$(date +%Y%m%d)}
VERIFY_TIMEOUT=${VERIFY_TIMEOUT:-180}
SOCK=$HERDR_CFG/herdr.sock
MIGRATE=${MIGRATE:-$(dirname "$(readlink -f "$0")")/migrate-herdr-resume.py}
LOCK_MARKER='# herdr-deploy-lock'
STOPPED=0
REPORT=()

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() { log "FAIL: $*"; exit 1; }
note() { REPORT+=("$*"); log "REPORT: $*"; }

# Every herdr CLI call reaches $SOCK, never an inherited or default socket.
hcall() {
    env -u HERDR_PANE_ID -u HERDR_CLIENT_SOCKET_PATH -u HERDR_ENV -u HERDR_WORKSPACE_ID -u HERDR_TAB_ID \
        HERDR_SOCKET_PATH="$SOCK" XDG_CONFIG_HOME="$(dirname "$HERDR_CFG")" "$@"
}

socket_pid() {
    ss -xlpn 2>/dev/null | awk -v sock="$SOCK" '$5 == sock' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2
}

relink() {
    ln -s "$VW_BASE/current/bin/herdr" "$BIN_DIR/.herdr.next.$$"
    mv -Tf "$BIN_DIR/.herdr.next.$$" "$BIN_DIR/herdr"
}

lock() {
    printf '#!/bin/sh\n%s\necho "herdr upgrade in progress - wait for DONE in %s" >&2\nexit 1\n' \
        "$LOCK_MARKER" "$RUN/log" >"$BIN_DIR/.herdr.lock.$$"
    chmod 755 "$BIN_DIR/.herdr.lock.$$"
    mv -Tf "$BIN_DIR/.herdr.lock.$$" "$BIN_DIR/herdr"
}

# Generalized promote.sh: a marked lock stub is replaced, never archived.
promote() {
    ln -s "releases/$1" "$VW_BASE/current.next.$$"
    mv -Tf "$VW_BASE/current.next.$$" "$VW_BASE/current"
    relink
}

start_server() { # start_server <binary>
    local cwd envv
    cwd=$(cat "$RUN/server.cwd")
    mapfile -d '' envv <"$RUN/server.environ"
    (cd "$cwd" && setsid -f env -i "${envv[@]}" "$1" server </dev/null >>"$RUN/server.out" 2>&1)
}

wait_gone() { # wait_gone <seconds> <pid>...
    local deadline=$((SECONDS + $1)); shift
    while [ $SECONDS -lt $deadline ]; do
        local alive=0
        for pid in "$@"; do kill -0 "$pid" 2>/dev/null && alive=1; done
        [ $alive = 0 ] && return 0
        sleep 0.5
    done
    return 1
}

render_config() {
    local shell line
    shell=$(command -v fish || true)
    while IFS= read -r line || [ -n "$line" ]; do
        printf '%s\n' "${line//@DEFAULT_SHELL@/$shell}"
    done <"$TEMPLATE" >"$RUN/config.toml"
}

stage() {
    local rel="$VW_BASE/releases/$NEW_REL"
    if [ ! -d "$rel" ]; then
        cp -al "$VW_BASE/releases/$OLD_REL" "$rel.tmp"
        cp "$NEW_BIN" "$rel.tmp/bin/.herdr.new"   # new inode: the old release stays intact
        mv -f "$rel.tmp/bin/.herdr.new" "$rel.tmp/bin/herdr"
        mv -T "$rel.tmp" "$rel"
        log "staged $rel"
    fi
    cmp -s "$rel/bin/herdr" "$NEW_BIN" || die "$rel/bin/herdr differs from $NEW_BIN"
}

preconditions() {
    "$NEW_BIN" --version | grep -q '^herdr 0\.9\.' || die "staged binary is not 0.9.x"
    HERDR_CONFIG_PATH="$RUN/config.toml" "$NEW_BIN" config check >/dev/null || die "rendered config fails config check"
    OLD_PID=$(socket_pid)
    [ -n "$OLD_PID" ] || die "no server listening on $SOCK"
    OLD_BIN=$(readlink -f "/proc/$OLD_PID/exe")
    for manifest in "$REVIEW_DIR"/adv_convo_*/manifest.json; do
        [ -e "$manifest" ] || continue
        grep -q '"status": "open"' "$manifest" && die "review still open: $manifest"
        [ -e "$(dirname "$manifest")/watchdog.pid" ] && die "review watchdog still running: $manifest"
    done
    printf '%s\n' "$OLD_REL" >"$RUN/old_rel"
    printf '%s\n' "$OLD_PID" >"$RUN/old_pid"
    cp "/proc/$OLD_PID/environ" "$RUN/server.environ"
    readlink "/proc/$OLD_PID/cwd" >"$RUN/server.cwd"
    cp "$HERDR_CFG/config.toml" "$RUN/config.before.toml"
    log "old server pid $OLD_PID ($OLD_BIN), release $OLD_REL -> $NEW_REL"
}

capture() {
    HERDR_CONFIG_PATH="$RUN/config.toml" HERDR_LIVE_SOCKET="$SOCK" HERDR_BIN="$OLD_BIN" \
        python3 "$MIGRATE" capture "$RUN/capture.json" "$HERDR_CFG/session.json"
    [ "$(socket_pid)" = "$OLD_PID" ] || die "socket owner changed during capture"
}

# Panes whose old codex outlived the stop lose their codex resume instead of
# colliding with its writer lock; the server still starts.
drop_codex_pane() {
    python3 - "$HERDR_CFG/session.json" "$1" <<'PY'
import json, sys
path, pane = sys.argv[1:]
alphabet = "123456789ABCDEFGHJKMNPQRSTVWXYZ0"
def enc(v):
    out = ""
    while v > 0:
        out = alphabet[(v - 1) % 32] + out
        v = (v - 1) // 32
    return out
data = json.load(open(path))
for ws in data["workspaces"]:
    for tab in ws.get("tabs", []):
        for key, p in tab.get("panes", {}).items():
            if f"{ws['id']}:p{enc(ws['public_pane_numbers'].get(key, 0))}" == pane:
                p.pop("agent_session", None); p.pop("agent_resume", None)
json.dump(data, open(path, "w"))
PY
}

install_integrations() {
    mkdir -p "$RUN/backup"
    cp -p "$CODEX_HOME_DIR/config.toml" "$RUN/backup/codex-config.toml" 2>/dev/null || true
    cp -p "$CODEX_HOME_DIR/hooks.json" "$RUN/backup/codex-hooks.json" 2>/dev/null || true
    cp -a "$PI_AGENT_DIR/extensions" "$RUN/backup/pi-extensions" 2>/dev/null || true
    for target in codex pi; do
        if CODEX_HOME="$CODEX_HOME_DIR" PI_CODING_AGENT_DIR="$PI_AGENT_DIR" \
            hcall "$VW_BASE/releases/$NEW_REL/bin/herdr" integration install "$target" >>"$RUN/log" 2>&1; then
            log "installed $target integration"
        else
            note "$target integration install FAILED (deploy continues): run 'herdr integration install $target'"
        fi
    done
}

verify() {
    local new_bin="$VW_BASE/releases/$NEW_REL/bin/herdr" deadline=$((SECONDS + 30)) pid=""
    while [ $SECONDS -lt $deadline ]; do
        pid=$(socket_pid)
        [ -n "$pid" ] && [ "$pid" != "$OLD_PID" ] && break
        sleep 0.5
    done
    [ -n "$pid" ] && [ "$pid" != "$OLD_PID" ] || return 1
    cmp -s "$(readlink -f "/proc/$pid/exe")" "$new_bin" || return 1
    if tr '\0' '\n' <"/proc/$pid/environ" | grep -qE '^(CLAUDE_CONFIG_DIR|HERDR_PANE_ID)='; then
        note "new server environment carries CLAUDE_CONFIG_DIR or HERDR_PANE_ID"
        return 1
    fi
    log "new server pid $pid running $new_bin"
    NEW_PID=$pid
    SOCK="$SOCK" VERIFY_TIMEOUT="$VERIFY_TIMEOUT" python3 - "$RUN/capture.json" "$HERDR_CFG/session.json" "$RUN/dropped" <<'PY' || return 2
import json, os, sys, time
cap = json.load(open(sys.argv[1])); dropped = set(open(sys.argv[3]).read().split()) if os.path.exists(sys.argv[3]) else set()
alphabet = "123456789ABCDEFGHJKMNPQRSTVWXYZ0"
def enc(v):
    out = ""
    while v > 0:
        out = alphabet[(v - 1) % 32] + out; v = (v - 1) // 32
    return out
final = {}
for ws in json.load(open(sys.argv[2]))["workspaces"]:
    for tab in ws.get("tabs", []):
        for key, p in tab.get("panes", {}).items():
            if p.get("agent_resume"):
                final[f"{ws['id']}:p{enc(ws['public_pane_numbers'].get(key, 0))}"] = p["agent_resume"]["argv"]
want = {pane: ("claude", e) for pane, e in cap["claude"].items()}
want.update({pane: ("codex", e) for pane, e in cap.get("codex", {}).items() if pane not in dropped})
sock = os.environ["SOCK"]
def procs():
    found = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
            if comm not in ("claude", "codex"):
                continue
            env = dict(e.split("=", 1) for e in open(f"/proc/{pid}/environ", "rb").read().decode(errors="replace").split("\0") if "=" in e)
            argv = open(f"/proc/{pid}/cmdline", "rb").read().decode().split("\0")[:-1]
        except OSError:
            continue
        if env.get("HERDR_SOCKET_PATH") == sock:
            found.setdefault((env.get("HERDR_PANE_ID"), comm), []).append((env, argv))
    return found
deadline = time.time() + int(os.environ["VERIFY_TIMEOUT"])
while True:
    seen, bad = procs(), {}
    for pane, (agent, e) in want.items():
        argv = final.get(pane)
        hits = seen.get((pane, agent), [])
        if not argv or not hits:
            bad[pane] = "no process yet"; continue
        env, live = hits[0]
        if live[-1] != argv[-1]:
            bad[pane] = f"argv {live} != {argv}"
        elif agent == "claude" and (env.get("CLAUDE_CONFIG_DIR") != e["config_dir"]
                                    or any(a in live for a in ("--dangerously-skip-permissions", "bypassPermissions")) != e["bypass"]):
            bad[pane] = f"config dir {env.get('CLAUDE_CONFIG_DIR')} / bypass mismatch"
    if not bad or time.time() > deadline:
        break
    time.sleep(2)
for pane in sorted(want):
    print(f"VERIFY {pane}: {'ok' if pane not in bad else 'MISMATCH ' + bad[pane]}  ({' '.join(final.get(pane, ['?']))})")
sys.exit(1 if bad else 0)
PY
}

fresh_pane_env_check() {
    local new_bin="$VW_BASE/releases/$NEW_REL/bin/herdr" ws pane
    ws=$(hcall "$new_bin" workspace create --label deploy-env-check --cwd /tmp | python3 -c 'import json,sys;r=json.load(sys.stdin)["result"];print(r["workspace"]["workspace_id"], r["root_pane"]["pane_id"])') || return 0
    pane=${ws#* }; ws=${ws% *}
    hcall "$new_bin" pane run "$pane" "env > $RUN/pane.env" >/dev/null 2>&1 || true
    for _ in $(seq 20); do [ -s "$RUN/pane.env" ] && break; sleep 0.5; done
    hcall "$new_bin" workspace close "$ws" >/dev/null 2>&1 || true
    if grep -q '^CLAUDE_CONFIG_DIR=' "$RUN/pane.env" 2>/dev/null; then note "fresh pane has CLAUDE_CONFIG_DIR"; fi
    if [ "$(grep '^HERDR_PANE_ID=' "$RUN/pane.env" 2>/dev/null | cut -d= -f2)" != "$pane" ]; then note "fresh pane HERDR_PANE_ID is not its own"; fi
}

rollback() {
    RUN=${1:-$WORK/deploy-last}
    RUN=$(readlink -f "$RUN")
    OLD_REL=$(cat "$RUN/old_rel")
    log "ROLLBACK from $RUN to release $OLD_REL"
    local pid exe
    pid=$(socket_pid)
    if [ -n "$pid" ]; then
        exe=$(readlink -f "/proc/$pid/exe")
        hcall "$exe" server stop >/dev/null 2>&1 || true
        wait_gone 60 "$pid" || die "a server ($pid, $exe) still owns $SOCK; refusing to start a second one"
    fi
    ln -s "releases/$OLD_REL" "$VW_BASE/current.next.$$"
    mv -Tf "$VW_BASE/current.next.$$" "$VW_BASE/current"
    relink
    python3 - "$RUN/config.before.toml" "$HERDR_CFG/config.toml" <<'PY'
import sys
text = open(sys.argv[1]).read()
if "[session]" in text:
    text = text.replace("[session]", "[session]\nresume_agents_on_restore = false", 1)
else:
    text = text.rstrip("\n") + "\n\n[session]\nresume_agents_on_restore = false\n"
open(sys.argv[2], "w").write(text)
PY
    [ -f "$RUN/session.final.json" ] && cp "$RUN/session.final.json" "$HERDR_CFG/session.json"
    start_server "$VW_BASE/releases/$OLD_REL/bin/herdr"
    log "old server started; agents were NOT resumed. Resume each by hand:"
    python3 - "$RUN/capture.json" "$RUN/session.final.json" <<'PY' || true
import json, os, sys
cap = json.load(open(sys.argv[1]))
final = {}
if os.path.exists(sys.argv[2]):
    alphabet = "123456789ABCDEFGHJKMNPQRSTVWXYZ0"
    def enc(v):
        out = ""
        while v > 0:
            out = alphabet[(v - 1) % 32] + out; v = (v - 1) // 32
        return out
    for ws in json.load(open(sys.argv[2]))["workspaces"]:
        for tab in ws.get("tabs", []):
            for key, p in tab.get("panes", {}).items():
                s = p.get("agent_session")
                if s:
                    final[f"{ws['id']}:p{enc(ws['public_pane_numbers'].get(key, 0))}"] = (s["value"], p.get("cwd"))
for pane, e in sorted(cap["claude"].items()):
    sid, cwd = final.get(pane, ("<id>", "?"))
    print(f"  {pane} (cwd {cwd}): {' '.join([e['variant'], *e['kept'], '--resume', sid])}")
for pane, e in sorted(cap.get("codex", {}).items()):
    print(f"  {pane} (cwd {e['cwd']}): {' '.join(e['argv'])}")
PY
}

on_error() {
    local line=$1
    if [ "$STOPPED" = 1 ]; then
        log "error at line $line after the stop: rolling back"
        STOPPED=0
        rollback "$RUN" || true
    else
        log "error at line $line before the stop: nothing stopped"
        [ "${LOCKED:-0}" = 1 ] && relink
    fi
    exit 1
}

main() {
    local mode=${1:-}
    if [ "$mode" = rollback ]; then rollback "${2:-}"; exit 0; fi
    [ "$mode" = dry-run ] || [ "$mode" = deploy ] || die "usage: deploy-herdr.sh dry-run|deploy|rollback [run dir]"
    [ -x "${NEW_BIN:-}" ] || die "NEW_BIN must point at the staged herdr binary"
    OLD_REL=$(readlink "$VW_BASE/current" | sed 's|^releases/||')
    RUN=$WORK/deploy-$(date +%Y%m%dT%H%M%S)
    mkdir -p "$RUN"
    exec > >(tee -a "$RUN/log") 2>&1
    trap 'on_error $LINENO' ERR
    log "$mode: new $NEW_BIN, release $NEW_REL, run dir $RUN"
    render_config
    stage
    preconditions
    if [ "$mode" = dry-run ]; then
        capture
        log "DRY RUN OK: nothing stopped, live config and links untouched"
        exit 0
    fi
    ln -sfn "$RUN" "$WORK/deploy-last"
    LOCKED=1; lock
    capture
    STOPPED=1
    hcall "$OLD_BIN" server stop >/dev/null 2>&1 || true
    wait_gone 60 "$OLD_PID" || die "old server $OLD_PID did not exit"
    local before=""
    while [ "$before" != "$(stat -c %Y.%s "$HERDR_CFG/session.json")" ]; do
        before=$(stat -c %Y.%s "$HERDR_CFG/session.json"); sleep 3
    done
    cp "$HERDR_CFG/session.json" "$RUN/session.final.json"
    python3 "$MIGRATE" apply "$RUN/capture.json" "$HERDR_CFG/session.json" | tee "$RUN/apply.txt"
    install_integrations
    cp "$RUN/config.toml" "$HERDR_CFG/config.toml"
    promote "$NEW_REL"; LOCKED=0
    : >"$RUN/dropped"
    for entry in $(python3 -c 'import json,sys;[print(f"{p}={e[\"pids\"][0]}") for p,e in json.load(open(sys.argv[1])).get("codex",{}).items()]' "$RUN/capture.json"); do
        if ! wait_gone 20 "${entry#*=}"; then
            drop_codex_pane "${entry%%=*}"
            echo "${entry%%=*}" >>"$RUN/dropped"
            note "${entry%%=*}: old codex ${entry#*=} still alive, not resumed - run its command from capture.json"
        fi
    done
    start_server "$VW_BASE/current/bin/herdr"
    local status=0
    verify || status=$?
    if [ "$status" = 1 ]; then die "new server did not come up correctly"; fi
    STOPPED=0
    [ "$status" = 2 ] && note "some panes did not verify, see VERIFY lines; resume them by hand from capture.json"
    fresh_pane_env_check
    if [ -f "$FISH_COMPLETIONS" ]; then
        "$VW_BASE/current/bin/herdr" completion fish >"$FISH_COMPLETIONS.tmp" && mv -f "$FISH_COMPLETIONS.tmp" "$FISH_COMPLETIONS"
    fi
    log "DONE. Reattach with: herdr"
    if python3 -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get("codex") else 1)' "$RUN/capture.json"; then
        log "codex panes open on 'Hooks need review': choose 'Trust all and continue' once."
    fi
    for line in "${REPORT[@]}"; do log "REPORT: $line"; done
}

main "$@"
