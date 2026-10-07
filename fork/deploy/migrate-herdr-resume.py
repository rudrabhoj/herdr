#!/usr/bin/env python3
"""One-time bridge for upgrading a pre-variant herdr server.

Old servers never recorded which Claude variant (claude-kee, claude-me, ...)
or flags each pane ran, so a plain upgrade restores every Claude pane as
`claude --resume <id>`. `capture` reads, per live pane, the variant and kept
flags from the running Claude process; after the old server has stopped,
`apply` writes them into its final snapshot as `agent_resume`, using the
session id the snapshot ended with.

    migrate-herdr-resume.py capture CAPTURE_JSON SESSION_JSON   # while panes run
    migrate-herdr-resume.py apply   CAPTURE_JSON SESSION_JSON   # after stop

Keyed by public pane id (HERDR_PANE_ID), not session id: a /clear or /resume
between capture and stop changes the session id, never the pane. A Claude
pane the capture does not cover loses its native resume rather than falling
back to `claude --resume` in the wrong account; its manual command is printed.

Variants and kept args come from the herdr config [session] section
(HERDR_CONFIG_PATH, else $XDG_CONFIG_HOME/herdr/config.toml); the live socket
from HERDR_LIVE_SOCKET, else the config dir's herdr.sock.
"""
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HOME = Path.home()
CONFIG = Path(os.environ.get("HERDR_CONFIG_PATH")
              or Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "herdr/config.toml")
ALPHABET = "123456789ABCDEFGHJKMNPQRSTVWXYZ0"  # src/workspace.rs PUBLIC_ID_ALPHABET
BYPASS = ("--dangerously-skip-permissions", "--permission-mode=bypassPermissions")


def encode_public_number(value):
    out = ""
    while value > 0:
        out = ALPHABET[(value - 1) % len(ALPHABET)] + out
        value = (value - 1) // len(ALPHABET)
    return out or "0"


def expand(value):
    return str(HOME / value[2:]) if value.startswith("~/") else value


def same(expected, actual):
    trim = lambda v: v.rstrip("/") if len(v) > 1 else v
    return trim(expected) == trim(actual)


def kept_args(argv, keep):
    """Mirror of src/agent_resume.rs kept_launch_args."""
    kept, i = [], 1
    while i < len(argv):
        arg = argv[i]
        for entry in keep:
            if entry.endswith("="):
                flag = entry[:-1]
                if arg.startswith(flag + "="):
                    kept.append(arg)
                elif arg == flag and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    kept += [arg, argv[i + 1]]
                    i += 1
            elif arg == entry:
                kept.append(arg)
        i += 1
    return kept


def bypass(argv):
    """Independent of the keep list: is permission bypass on in this argv?"""
    joined = [f"{a}={argv[i + 1]}" if a == "--permission-mode" and i + 1 < len(argv) else a
              for i, a in enumerate(argv)]
    return any(a in BYPASS for a in joined)


def snapshot_claude_panes(data):
    """(public id or None, snapshot key, pane) for every Claude pane in a snapshot."""
    for ws in data["workspaces"]:
        numbers = ws.get("public_pane_numbers", {})
        for tab in ws.get("tabs", []):
            for key, pane in tab.get("panes", {}).items():
                session = pane.get("agent_session")
                if isinstance(session, dict) and session.get("agent") == "claude":
                    public = f"{ws['id']}:p{encode_public_number(numbers[key])}" if key in numbers else None
                    yield public, f"{ws['id']}/{key}", pane


UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def codex_argv(argv, keep, session_id):
    """Mirror of launch_profile for codex: kept args follow the subcommand."""
    return ["codex", "resume", *kept_args(argv, keep), session_id]


def live_codex_panes(socket):
    """Codex panes as the live server sees them, independent of /proc."""
    herdr = os.environ.get("HERDR_BIN", str(HOME / ".local/bin/herdr"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
    env["HERDR_SOCKET_PATH"] = socket
    out = subprocess.run([herdr, "pane", "list"], env=env, capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        raise SystemExit(f"herdr pane list failed: {out.stderr.strip()}")
    return {p["pane_id"]: p.get("cwd") for p in json.loads(out.stdout)["result"]["panes"]
            if p.get("agent") == "codex"}


def capture_codex(socket, keep, problems):
    expected = live_codex_panes(socket)
    found = {}
    for pid in sorted(int(p) for p in os.listdir("/proc") if p.isdigit()):
        try:
            if Path(f"/proc/{pid}/comm").read_text().strip() != "codex":
                continue
            env = dict(e.split("=", 1) for e in
                       Path(f"/proc/{pid}/environ").read_bytes().decode(errors="replace").split("\0") if "=" in e)
            if env.get("HERDR_SOCKET_PATH") != socket:
                continue
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")[:-1]
            fds = [os.readlink(f"/proc/{pid}/fd/{fd}") for fd in os.listdir(f"/proc/{pid}/fd")]
        except OSError:
            continue
        pane = env.get("HERDR_PANE_ID")
        rollouts = sorted({m.group(1) for f in fds if (m := re.search(rf"/sessions/.*rollout-.*-({UUID})\.jsonl$", f))})
        locks = sorted({m.group(1) for f in fds if (m := re.search(rf"/thread-writer-locks/({UUID})\.lock$", f))})
        if len(locks) != 1 or rollouts != locks:
            problems.append(f"{pane}: codex pid {pid} has rollouts {rollouts} and writer locks {locks}, need exactly one matching pair")
            continue
        if pane in found:
            problems.append(f"{pane}: two codex processes with sessions")
            continue
        found[pane] = {"pids": [pid], "session": locks[0], "cwd": expected.get(pane),
                       "argv": codex_argv(argv, keep, locks[0])}
        print(f"{pane}: {' '.join(found[pane]['argv'][:-1])} <id>")
    for pane in sorted(set(expected) - set(found)):
        problems.append(f"{pane}: codex pane on the live server but not captured")
    for pane in sorted(set(found) - set(expected)):
        problems.append(f"{pane}: codex captured but not a codex pane on the live server")
    return found


def capture(out, session_file):
    session = tomllib.loads(CONFIG.read_text()).get("session", {})
    variants = [v for v in session.get("agent_variants", []) if v.get("agent") == "claude"]
    keep = session.get("resume_keep_args", {}).get("claude", [])
    live_socket = os.environ.get("HERDR_LIVE_SOCKET", str(CONFIG.parent / "herdr.sock"))
    found, problems = {}, []
    for pid in sorted(int(p) for p in os.listdir("/proc") if p.isdigit()):
        try:
            if Path(f"/proc/{pid}/comm").read_text().strip() != "claude":
                continue
            env = dict(e.split("=", 1) for e in
                       Path(f"/proc/{pid}/environ").read_bytes().decode(errors="replace").split("\0") if "=" in e)
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")[:-1]
        except OSError:
            continue
        if env.get("HERDR_SOCKET_PATH") != live_socket:
            continue
        pane = env.get("HERDR_PANE_ID")
        variant = next((v["name"] for v in variants if all(
            same(expand(want), env.get(name, "")) for name, want in v.get("env", {}).items())), "claude")
        kept = kept_args(argv, keep)
        if bypass(argv) != bypass([variant, *kept]):
            problems.append(f"{pane}: bypass {bypass(argv)} in process, {bypass([variant, *kept])} after keep list")
        if pane in found:
            problems.append(f"{pane}: two claude processes")
        found[pane] = {"pid": pid, "variant": variant, "kept": kept,
                       "config_dir": env.get("CLAUDE_CONFIG_DIR"), "bypass": bypass(argv)}
        print(f"{pane}: {' '.join([variant, *kept])} --resume <id>")
    # The expected set comes from the server's own snapshot, not from /proc, so
    # a capture that silently matched nothing (wrong socket, renamed binary,
    # unreadable environ) cannot pass.
    expected = {public or key for public, key, _ in
                snapshot_claude_panes(json.loads(Path(session_file).read_text()))}
    if not expected:
        problems.append("snapshot has no claude panes")
    for pane in sorted(expected - set(found)):
        problems.append(f"{pane}: claude pane in the snapshot but not captured")
    for pane in sorted(set(found) - expected):
        problems.append(f"{pane}: captured but not a claude pane in the snapshot (save pending?)")
    # Codex last: its session cannot be corrected from the snapshot later.
    codex_keep = session.get("resume_keep_args", {}).get("codex", [])
    codex = capture_codex(live_socket, codex_keep, problems)
    Path(out).write_text(json.dumps({"claude": found, "codex": codex}, indent=2))
    print(f"captured {len(found)} of {len(expected)} snapshot claude panes and {len(codex)} codex panes -> {out}")
    for line in problems:
        print("PROBLEM", line)
    sys.exit(1 if problems else 0)


def apply(capture_file, session_file):
    captured = json.loads(Path(capture_file).read_text())
    found, codex = captured["claude"], captured.get("codex", {})
    data = json.loads(Path(session_file).read_text())
    patched, dropped = [], []
    for public, key, pane in list(snapshot_claude_panes(data)):
        session = pane["agent_session"]
        entry = found.get(public)
        if entry is None:
            # Variant and flags are unknown here; never suggest plain claude.
            dropped.append(f"{public or key}: variant UNKNOWN, session {session['value']}, cwd {pane.get('cwd')}"
                           f" - resume with the account it ran in: <claude-kee|claude-me|claude> --resume {session['value']}")
            del pane["agent_session"]
            continue
        pane["agent_resume"] = {"source": session["source"], "agent": "claude",
                                "argv": [entry["variant"], *entry["kept"], "--resume", session["value"]]}
        patched.append(public)
    for ws in data["workspaces"]:
        numbers = ws.get("public_pane_numbers", {})
        for tab in ws.get("tabs", []):
            for key, pane in tab.get("panes", {}).items():
                public = f"{ws['id']}:p{encode_public_number(numbers[key])}" if key in numbers else None
                entry = codex.get(public)
                if entry is None:
                    continue
                pane["agent_session"] = {"source": "herdr:codex", "agent": "codex", "kind": "id",
                                         "value": entry["session"]}
                pane["agent_resume"] = {"source": "herdr:codex", "agent": "codex", "argv": entry["argv"]}
                patched.append(public)
    for pane in sorted(set(codex) - set(patched)):
        print(f"NOT RESUMED (codex pane not in snapshot): {pane}: {' '.join(codex[pane]['argv'])}"
              f" (cwd {codex[pane]['cwd']})")
    backup = Path(session_file).with_suffix(".json.pre-variant-migration")
    backup.write_text(Path(session_file).read_text())
    Path(session_file).write_text(json.dumps(data))
    print(f"patched {len(patched)} panes; backup at {backup}")
    for line in dropped:
        print(f"NOT RESUMED (run by hand): {line}")
    missing = set(found) - set(patched) - set(codex)
    for pane in sorted(missing):
        print(f"captured but not in snapshot: {pane}")


def selftest():
    """The codex command must equal what herdr's launch_profile re-derives
    after restore (src/agent_resume.rs launch_profile_places_kept_args_after_a_subcommand),
    or the first detection rewrites it."""
    keep = ["--dangerously-bypass-approvals-and-sandbox", "--search", "-m=", "--model="]
    argv = ["node", "/home/me/.local/share/nvm/v24/bin/codex", "-m", "gpt-6-astra", "-c",
            "model_reasoning_effort=high", "--search", "--dangerously-bypass-approvals-and-sandbox"]
    got = codex_argv(argv, keep, "01a108ae")
    want = ["codex", "resume", "-m", "gpt-6-astra", "--search",
            "--dangerously-bypass-approvals-and-sandbox", "01a108ae"]
    assert got == want, got
    assert encode_public_number(28) == "W" and encode_public_number(10) == "A"
    print("selftest ok")


if __name__ == "__main__":
    {"capture": capture, "apply": apply, "selftest": selftest}[sys.argv[1]](*sys.argv[2:])
