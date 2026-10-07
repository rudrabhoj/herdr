#!/usr/bin/env python3
"""End-to-end: herdr shows and restores the Claude variant a pane last ran.

Isolated XDG root, HERDR_* stripped; real fish + claude-kee/claude-me in a
throwaway directory. The live herdr and its sessions are never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pexpect

HERDR, TEMPLATE = sys.argv[1], Path(sys.argv[2])
ROOT = Path("/tmp/claude-1000/hv")
WORK = Path("/tmp/claude-1000/cc-herdr-e2e")
HOME = Path.home()
ENV = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
ENV.pop("CLAUDE_CONFIG_DIR", None)
# Herdr keeps config/sockets/session under XDG_CONFIG_HOME and caches under
# XDG_STATE_HOME. XDG_DATA_HOME stays real: Claude's installer keys off it and
# would repoint ~/.local/bin/claude into the test root. The updater is off too.
ENV.update(XDG_CONFIG_HOME=str(ROOT / "c"), XDG_STATE_HOME=str(ROOT / "s"),
           XDG_CACHE_HOME=str(ROOT / "k"), DISABLE_AUTOUPDATER="1",
           TERM="xterm-256color", fish_history="")
CLAUDE_LINK = HOME / ".local/bin/claude"
CLAUDE_TARGET = os.readlink(CLAUDE_LINK)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def cli(*args):
    out = subprocess.run([HERDR, *args], env=ENV, capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {out.stderr or out.stdout}")
    return json.loads(out.stdout)["result"] if out.stdout.startswith("{") else out.stdout


def wait(predicate, seconds=30, step=0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (RuntimeError, KeyError, StopIteration, ValueError, OSError):
            pass
        time.sleep(step)
    return None


def test_claudes():
    """Claude processes belonging to the isolated server, with env and argv."""
    found = []
    for pid in subprocess.run(["pgrep", "-x", "claude"], capture_output=True, text=True).stdout.split():
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")[:-1]
        except OSError:
            continue
        env = dict(e.decode(errors="replace").split("=", 1) for e in environ if b"=" in e)
        if env.get("HERDR_SOCKET_PATH", "").startswith(str(ROOT)):
            found.append({"pid": int(pid), "env": env, "argv": argv})
    return found


def pane_text(pane):
    return cli("pane", "read", pane, "--source", "visible", "--lines", "60")


def accept_trust_if_asked(pane):
    # The trust prompt defaults to "No, exit"; pick "Yes, I trust this folder".
    if wait(lambda: "trust this folder" in pane_text(pane).lower(), seconds=8):
        cli("pane", "send-keys", pane, "down")
        time.sleep(0.3)
        cli("pane", "send-keys", pane, "enter")


def pane_info(pane):
    info = dict(cli("pane", "get", pane)["pane"])
    for agent in cli("agent", "list")["agents"]:
        if agent.get("pane_id") == pane:
            info.update({k: v for k, v in agent.items() if v is not None})
    return info


def saved_resume():
    session = ROOT / "c/herdr/session.json"
    data = json.loads(session.read_text())
    hits = []

    def walk(node):
        if isinstance(node, dict):
            if "agent_resume" in node and node["agent_resume"]:
                hits.append(node["agent_resume"]["argv"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(data)
    return hits


def attach():
    child = pexpect.spawn(HERDR, [], env=ENV, cwd=str(WORK), encoding="utf-8",
                          codec_errors="replace", timeout=20, dimensions=(40, 160))
    return child


def pump(child, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            child.read_nonblocking(65536, timeout=0.2)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            return


def restart(child):
    cli("server", "stop")
    child.close(force=True)
    wait(lambda: not test_claudes(), seconds=15)
    new = attach()
    pump(new, 3)
    return new


def ask(pane, prompt, expect, seconds=120):
    cli("pane", "send-text", pane, prompt)
    time.sleep(0.5)
    cli("pane", "send-keys", pane, "enter")
    return wait(lambda: expect in pane_text(pane), seconds, step=1)


def bypass_on(pane):
    return wait(lambda: "bypass permissions on" in pane_text(pane).lower(), 20)


def exit_claude(pane):
    cli("pane", "send-text", pane, "/exit")
    time.sleep(0.5)
    cli("pane", "send-keys", pane, "enter")
    return wait(lambda: not test_claudes(), 20)


def launch(pane, command):
    cli("pane", "run", pane, command)
    accept_trust_if_asked(pane)
    return wait(lambda: test_claudes(), 30)


def stage(child, pane, command, label, expect_env, flag, session_id, codeword):
    """Run  in the pane, check display + saved resume, restart herdr,
    check the restored process, its permission mode, and the conversation."""
    check(f"[{label}] started", launch(pane, command))
    check(f"[{label}] herdr shows the pane as {label}",
          wait(lambda: pane_info(pane).get("display_agent") == label, 30),
          json.dumps(pane_info(pane))[:300])
    want = [label] + (["--dangerously-skip-permissions"] if flag else [])
    saved = wait(lambda: [r for r in saved_resume() if r[0] == label], 20)
    sid = session_id or (saved and saved[0][-1])
    check(f"[{label}] saved resume is {' '.join(want)} --resume <id>",
          saved and saved[0] == want + ["--resume", sid], str(saved_resume()))
    if session_id is None:
        check(f"[{label}] conversation turn answered",
              ask(pane, f"Remember the codeword {codeword}. Reply with only OK.", "OK"))
    child = restart(child)
    restored = wait(lambda: test_claudes(), 40)
    proc = restored[0] if restored else {"env": {}, "argv": []}
    print(f"   [{label}] restored argv: {proc['argv']}", flush=True)
    check(f"[{label}] restored with CLAUDE_CONFIG_DIR={expect_env or '<unset>'}",
          proc["env"].get("CLAUDE_CONFIG_DIR") == expect_env, str(proc["env"].get("CLAUDE_CONFIG_DIR")))
    check(f"[{label}] restored argv resumes the same session",
          proc["argv"][-2:] == ["--resume", sid], str(proc["argv"]))
    check(f"[{label}] restored {'with' if flag else 'without'} --dangerously-skip-permissions",
          ("--dangerously-skip-permissions" in proc["argv"]) == flag, str(proc["argv"]))
    # The restored Claude names its own pane; the list also holds the default
    # workspace's empty pane.
    pane = proc["env"].get("HERDR_PANE_ID", pane)
    check(f"[{label}] restored pane still shown as {label}",
          wait(lambda: pane_info(pane).get("display_agent") == label, 30))
    on = bypass_on(pane)
    check(f"[{label}] Claude UI bypass mode is {'on' if flag else 'off'}", bool(on) == flag,
          pane_text(pane)[-300:])
    check(f"[{label}] restored session remembers the codeword",
          ask(pane, "What codeword did I give you earlier? Reply with only the codeword.", codeword))
    check(f"[{label}] exited cleanly", exit_claude(pane))
    return child, pane, sid


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    cfg = ROOT / "c/herdr/config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(TEMPLATE.read_text().replace("@DEFAULT_SHELL@", shutil.which("fish")))
    # XDG_CONFIG_HOME isolates herdr but also moves fish's config; pane shells
    # get a copy so claude-kee/claude-me exist without writing the real one.
    shutil.copytree(HOME / ".config/fish", ROOT / "c/fish", symlinks=True)
    codeword = f"KIWI-{int(time.time()) % 100000}"

    child = attach()
    try:
        pump(child, 2)
        check("isolated server up", wait(lambda: cli("workspace", "list")["workspaces"], 20))
        pane = cli("workspace", "create", "--label", "variants", "--cwd", str(WORK),
                   "--focus")["root_pane"]["pane_id"]
        pump(child, 2)
        kee, me = str(HOME / ".claude-keemakr"), str(HOME / ".claude")
        # 1. new session in claude-kee with the bypass flag
        child, pane, sid = stage(child, pane, "claude-kee --dangerously-skip-permissions",
                                 "claude-kee", kee, True, None, codeword)
        # 2. same session continued in claude-me, no flag
        child, pane, _ = stage(child, pane, f"claude-me --resume {sid}",
                               "claude-me", me, False, sid, codeword)
        # 3. same session in plain claude with the flag
        child, pane, _ = stage(child, pane, f"claude --dangerously-skip-permissions --resume {sid}",
                               "claude", None, True, sid, codeword)
        # 4. back to claude-kee without the flag
        child, pane, _ = stage(child, pane, f"claude-kee --resume {sid}",
                               "claude-kee", kee, False, sid, codeword)
    finally:
        subprocess.run([HERDR, "server", "stop"], env=ENV, capture_output=True, timeout=20)
        child.close(force=True)
        wait(lambda: not test_claudes(), 15)
        for proc in test_claudes():
            os.kill(proc["pid"], 9)

    check("isolated claude processes all gone", not test_claudes())
    check("real ~/.local/bin/claude untouched", os.readlink(CLAUDE_LINK) == CLAUDE_TARGET,
          os.readlink(CLAUDE_LINK))
    failed = [name for name, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if not failed:
        shutil.rmtree(ROOT, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
