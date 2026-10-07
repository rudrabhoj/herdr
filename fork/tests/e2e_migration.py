#!/usr/bin/env python3
"""Rehearse the live upgrade: new herdr restoring a patched copy of the real
0.8.0 snapshot. Every Claude session id is swapped for a fake one first, so
the restored Claudes can never open a live session."""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pexpect

HERDR, TEMPLATE, CAPTURE = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
MIGRATE = Path.home() / ".local/share/claude-accounts/migrate-herdr-resume.py"
ROOT = Path("/tmp/claude-1000/hm")
HOME = Path.home()
ENV = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
ENV.pop("CLAUDE_CONFIG_DIR", None)
ENV.update(XDG_CONFIG_HOME=str(ROOT / "c"), XDG_STATE_HOME=str(ROOT / "s"),
           XDG_CACHE_HOME=str(ROOT / "k"), DISABLE_AUTOUPDATER="1",
           TERM="xterm-256color", fish_history="")
CLAUDE_LINK = HOME / ".local/bin/claude"
CLAUDE_TARGET = os.readlink(CLAUDE_LINK)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def cli(*args):
    out = subprocess.run([HERDR, *args], env=ENV, capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        raise RuntimeError(out.stderr or out.stdout)
    return json.loads(out.stdout)["result"] if out.stdout.startswith("{") else out.stdout


def test_claude_pids():
    pids = []
    for pid in subprocess.run(["pgrep", "-x", "claude"], capture_output=True, text=True).stdout.split():
        try:
            if f"HERDR_SOCKET_PATH={ROOT}".encode() in Path(f"/proc/{pid}/environ").read_bytes():
                pids.append(int(pid))
        except OSError:
            pass
    return pids


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    (ROOT / "c/herdr").mkdir(parents=True)
    (ROOT / "c/herdr/config.toml").write_text(
        TEMPLATE.read_text().replace("@DEFAULT_SHELL@", shutil.which("fish")))
    shutil.copytree(HOME / ".config/fish", ROOT / "c/fish", symlinks=True)

    # Fake ids everywhere, consistently in the snapshot copy and the capture.
    snapshot = json.loads((HOME / ".config/herdr/session.json").read_text())
    captured = json.loads(CAPTURE.read_text())
    fake = {real: str(uuid.uuid4()) for real in captured}
    seen = []

    def swap(node):
        if isinstance(node, dict):
            session = node.get("agent_session")
            if isinstance(session, dict) and session.get("agent") == "claude":
                session["value"] = fake.setdefault(session["value"], str(uuid.uuid4()))
                seen.append(session["value"])
            for value in node.values():
                swap(value)
        elif isinstance(node, list):
            for value in node:
                swap(value)
    swap(snapshot)
    session_file = ROOT / "c/herdr/session.json"
    session_file.write_text(json.dumps(snapshot))
    fake_capture = {fake[real]: {**entry, "argv": entry["argv"][:-1] + [fake[real]]}
                    for real, entry in captured.items()}
    (ROOT / "capture.json").write_text(json.dumps(fake_capture))
    expected = {fid: entry["argv"] for fid, entry in fake_capture.items() if fid in seen}
    print(f"snapshot claude panes: {len(seen)}, captured live: {len(captured)}, matched: {len(expected)}")

    out = subprocess.run([sys.executable, str(MIGRATE), "apply", str(ROOT / "capture.json"),
                          str(session_file)], capture_output=True, text=True)
    print(out.stdout.strip())
    check("migration apply succeeds", out.returncode == 0, out.stderr)
    patched = json.loads(session_file.read_text())
    resumes = []

    def collect(node):
        if isinstance(node, dict):
            if node.get("agent_resume"):
                resumes.append(node["agent_resume"]["argv"])
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
    collect(patched)
    check("every matched claude pane got an agent_resume", len(resumes) == len(expected),
          f"{len(resumes)} vs {len(expected)}")

    child = pexpect.spawn(HERDR, [], env=ENV, cwd=str(ROOT), encoding="utf-8",
                          codec_errors="replace", timeout=20, dimensions=(40, 160))
    try:
        deadline = time.monotonic() + 60
        texts = {}
        while time.monotonic() < deadline:
            try:
                child.read_nonblocking(65536, timeout=0.5)
            except (pexpect.TIMEOUT, pexpect.EOF):
                pass
            try:
                panes = cli("pane", "list")["panes"]
            except RuntimeError:
                continue
            texts = {}
            for pane in panes:
                try:
                    texts[pane["pane_id"]] = cli("pane", "read", pane["pane_id"], "--source",
                                                 "recent", "--lines", "200")
                except RuntimeError:
                    pass
            typed = [argv for argv in expected.values()
                     if any(" ".join(argv) in text for text in texts.values())]
            if len(typed) == len(expected):
                break
        live_ws = len(snapshot["workspaces"])
        check(f"new server restored all {live_ws} workspaces from the 0.8.0 snapshot",
              len(cli("workspace", "list")["workspaces"]) == live_ws)
        for fid, argv in expected.items():
            line = " ".join(argv)
            check(f"typed: {line[:-36]}<id>", any(line in t for t in texts.values()))
        plain = [t for t in texts.values() if "claude --resume" in t and "claude-kee" not in t]
        check("no kee pane fell back to plain `claude --resume`",
              sum("claude-kee" in " ".join(a) for a in expected.values())
              == sum(any(" ".join(a) in t for t in texts.values()) for a in expected.values()
                     if a[0] == "claude-kee"))
    finally:
        subprocess.run([HERDR, "server", "stop"], env=ENV, capture_output=True, timeout=30)
        child.close(force=True)
        time.sleep(2)
        for pid in test_claude_pids():
            os.kill(pid, 9)
    check("no isolated claude left", not test_claude_pids())
    check("real ~/.local/bin/claude untouched", os.readlink(CLAUDE_LINK) == CLAUDE_TARGET)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    shutil.rmtree(ROOT, ignore_errors=True)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
