#!/usr/bin/env python3
"""Real-Claude angles the stand-ins cannot prove (one haiku call in total):
in-session /clear and /resume move herdr's recorded session, and claude-me's
/resume picker lists a session claude-kee created. Throwaway sessions only,
under a /tmp cwd, asserted absent from the live snapshot, deleted afterwards."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
NEW = sys.argv[1]
ROOT = Path("/tmp/claude-1000/ca")
WORK = Path("/tmp/claude-1000/ca-w")
RESULTS = []
LIVE_IDS = {p.get("agent_session", {}).get("value")
            for ws in json.loads((HOME / ".config/herdr/session.json").read_text())["workspaces"]
            for t in ws["tabs"] for p in t["panes"].values()}
ENV = {k: v for k, v in os.environ.items()
       if not k.startswith("HERDR_") and k != "CLAUDE_CONFIG_DIR" and not k.startswith("CLAUDE_CODE")}
ENV.update(XDG_CONFIG_HOME=str(ROOT / "c"), XDG_STATE_HOME=str(ROOT / "s"), XDG_CACHE_HOME=str(ROOT / "k"),
           DISABLE_AUTOUPDATER="1", TERM="xterm-256color", fish_history="")
SOCK = ROOT / "c/herdr/herdr.sock"
CREATED = set()


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def cli(*args):
    out = subprocess.run([NEW, *args], env=dict(ENV, HERDR_SOCKET_PATH=str(SOCK)),
                         capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise RuntimeError(out.stderr)
    return json.loads(out.stdout)["result"] if out.stdout.startswith("{") else out.stdout


def wait(predicate, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.5)
    return None


def text(pane):
    return cli("pane", "read", pane, "--source", "visible", "--lines", "60")


def send(pane, line):
    cli("pane", "send-text", pane, line)
    time.sleep(0.4)
    cli("pane", "send-keys", pane, "enter")


def trust(pane):
    if wait(lambda: "trust this folder" in text(pane).lower(), 10):
        cli("pane", "send-keys", pane, "down")
        time.sleep(0.3)
        cli("pane", "send-keys", pane, "enter")


def saved_id():
    data = json.loads((ROOT / "c/herdr/session.json").read_text())
    for ws in data["workspaces"]:
        for t in ws["tabs"]:
            for p in t["panes"].values():
                if p.get("agent_resume"):
                    return p["agent_resume"]["argv"][-1]


def claude_pids():
    found = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            if f"HERDR_SOCKET_PATH={SOCK}".encode() in Path(f"/proc/{pid}/environ").read_bytes():
                found.append(int(pid))
        except OSError:
            pass
    return found


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    (ROOT / "c/herdr").mkdir(parents=True)
    WORK.mkdir(parents=True)
    shutil.copytree(HOME / ".config/fish", ROOT / "c/fish", symlinks=True)
    (ROOT / "c/herdr/config.toml").write_text(
        (HOME / "Dev/herdr_and_claude/herdr/herdr.config.toml").read_text().replace("@DEFAULT_SHELL@", shutil.which("fish")))
    seed = subprocess.run(["claude", "-p", "--model", "haiku", "--output-format", "json", "Reply with only: OK"],
                          env=dict(ENV, CLAUDE_CONFIG_DIR=str(HOME / ".claude-keemakr")), cwd=WORK,
                          capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
    s0 = json.loads(seed.stdout.strip().splitlines()[-1])["session_id"]
    CREATED.add(s0)
    check("throwaway seed session is not a live session", s0 not in LIVE_IDS)
    subprocess.Popen(["setsid", "-f", NEW, "server"], env=ENV, cwd=str(ROOT),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait(lambda: SOCK.exists(), 20)
    pane = cli("workspace", "create", "--label", "angles", "--cwd", str(WORK))["root_pane"]["pane_id"]
    time.sleep(1.5)
    try:
        cli("pane", "run", pane, "claude-kee")
        trust(pane)
        s1 = wait(saved_id, 40)
        CREATED.add(s1)
        check("startup session recorded", s1 and s1 not in LIVE_IDS, str(s1))
        send(pane, "/clear")
        s2 = wait(lambda: saved_id() not in (None, s1) and saved_id(), 40)
        CREATED.add(s2)
        check("/clear moves the recorded resume to the new session", s2 and s2 != s1, f"{s1} -> {s2}")
        send(pane, f"/resume {s0}")
        check("/resume <id> moves the recorded resume to that session", wait(lambda: saved_id() == s0, 40),
              str(saved_id()))
        send(pane, "/exit")
        wait(lambda: not claude_pids(), 20)
        cli("pane", "run", pane, "claude-me --resume")
        trust(pane)
        check("claude-me's /resume picker lists the claude-kee session",
              # The picker hides -p sessions; the interactive kee session shows by its /clear entry.
              wait(lambda: "/clear" in text(pane) and "Esc to cancel" in text(pane), 40), text(pane)[-400:])
        cli("pane", "send-keys", pane, "esc")
        time.sleep(0.5)
        send(pane, "/exit")
    finally:
        try:
            cli("server", "stop")
        except Exception:
            pass
        wait(lambda: not claude_pids(), 20)
        for pid in claude_pids():
            os.kill(pid, 9)
        check("no isolated claude left", not claude_pids())
        project = "-" + str(WORK).strip("/").replace("/", "-")
        for base in (HOME / ".claude-keemakr",):
            shutil.rmtree(base / "projects" / project, ignore_errors=True)
            for sid in filter(None, CREATED):
                for d in ("session-env", "file-history", "tasks", "todos"):
                    shutil.rmtree(base / d / sid, ignore_errors=True)
        shutil.rmtree(ROOT, ignore_errors=True)
        shutil.rmtree(WORK, ignore_errors=True)
        print("throwaway sessions removed:", sorted(filter(None, CREATED)))
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
