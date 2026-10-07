#!/usr/bin/env python3
"""Rehearse Phases 11-12 with stand-in agents: no model call, no real login.

A: new server - account labels follow login changes (claude, codex, pi),
   restore commands, restart restores each stub with the exact argv.
B: deploy-herdr.sh from the operator's env on an isolated old server with a
   claude-kee, a plain claude and a codex pane, an injected codex install
   failure, then rollback.
C: failure injected at the apply step: automatic rollback, no lock left.
Every root is under /tmp/claude-1000/d?; the live herdr is checked unchanged.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

HOME = Path.home()
NEW = Path(sys.argv[1])
OLD = Path(os.path.realpath(HOME / ".local/share/void-workstation/releases/20260906/bin/herdr"))
REPO = HOME / "Dev/herdr_and_claude/herdr"
ACCOUNTS = HOME / ".local/share/claude-accounts"
RESULTS = []
LIVE = {"bin": os.readlink(HOME / ".local/bin/herdr"),
        "current": os.readlink(HOME / ".local/share/void-workstation/current")}


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def live_server_pid():
    out = subprocess.run(["ss", "-xlpn"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f" {HOME}/.config/herdr/herdr.sock " in line and "pid=" in line:
            return line.split("pid=")[1].split(",")[0]
    return None


LIVE["pid"] = live_server_pid()


def jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def wait(predicate, seconds=30, step=0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(step)
    return None


class Root:
    def __init__(self, name):
        self.r = Path(f"/tmp/claude-1000/{name}")
        shutil.rmtree(self.r, ignore_errors=True)
        for d in ("c/herdr", "s", "k", "stubs", "log", "codex", "pi/agent/extensions",
                  "ctest", "work/tests", "bin", "vw/releases/old/bin", "none"):
            (self.r / d).mkdir(parents=True)
        shutil.copytree(HOME / ".config/fish", self.r / "c/fish", symlinks=True)
        (self.r / "c/fish/conf.d/claude-test.fish").write_text(
            f'function claude-test\n    set -lx CLAUDE_CONFIG_DIR "{self.r}/ctest"\n    command claude $argv\nend\n')
        # Stand-ins must win over the owner's fish_user_paths (~/.local/bin),
        # or the REAL claude/pi start inside the rehearsal.
        with open(self.r / "c/fish/config.fish", "a") as config:
            config.write(f'\nset -gx PATH {self.r}/stubs $PATH\n')
        self.write_stubs()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("HERDR_") and k != "CLAUDE_CONFIG_DIR" and not k.startswith("CLAUDE_CODE")}
        self.env.update(XDG_CONFIG_HOME=str(self.r / "c"), XDG_STATE_HOME=str(self.r / "s"),
                        XDG_CACHE_HOME=str(self.r / "k"), PATH=f"{self.r}/stubs:{os.environ['PATH']}",
                        STUB_LOG=str(self.r / "log"), CODEX_HOME=str(self.r / "codex"),
                        PI_CODING_AGENT_DIR=str(self.r / "pi/agent"), DISABLE_AUTOUPDATER="1",
                        TERM="xterm-256color", fish_history="")
        self.sock = self.r / "c/herdr/herdr.sock"
        which = subprocess.run(["fish", "-c", "command -v claude codex pi"], env=self.env,
                               capture_output=True, text=True).stdout.split()
        if which != [f"{self.r}/stubs/{n}" for n in ("claude", "codex", "pi")]:
            raise SystemExit(f"ABORT: fish would run real agents: {which}")

    def write_stubs(self):
        stubs = self.r / "stubs"
        (stubs / "claude").write_text(
            '#!/bin/bash\n{ echo "CONFIG=${CLAUDE_CONFIG_DIR:-}"; printf "%s\\n" "$@"; } > "$STUB_LOG/claude-$$.args"\n'
            'while :; do sleep 60; done\n')
        (stubs / "codex").write_text(
            '#!/bin/bash\nif [ "$1" = resume ]; then id=${@: -1}; else id=$(cat /proc/sys/kernel/random/uuid); fi\n'
            'd="$CODEX_HOME/sessions/2026/10/07"; mkdir -p "$d" "$CODEX_HOME/thread-writer-locks"\n'
            'exec 3>>"$d/rollout-2026-10-07T00-00-00-$id.jsonl" 4>>"$CODEX_HOME/thread-writer-locks/$id.lock"\n'
            'printf "%s\\n" "$@" > "$STUB_LOG/codex-$$.args"\nwhile :; do sleep 60; done\n')
        ext = self.r / "pi/agent/extensions/herdr-agent-state.ts"
        (stubs / "pi").write_text(f'''#!/usr/bin/env node
process.title = "pi";
const fs = require("node:fs");
fs.writeFileSync(`${{process.env.STUB_LOG}}/pi-${{process.pid}}.args`, process.argv.slice(2).join("\\n"));
const handlers = new Map();
const pi = {{ on: (e, h) => handlers.set(e, h), events: {{ on: () => () => {{}} }} }};
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const token = () => `h.${{b64({{ "https://api.openai.com/profile": {{ email: fs.readFileSync(process.env.STUB_LOG + "/pi-email", "utf8").trim() }} }})}}.s`;
const ctx = {{ mode: "tui", hasUI: true, isIdle: () => true,
  sessionManager: {{ getSessionFile: () => "{self.r}/pi/s.jsonl", getSessionId: () => "s" }},
  model: {{ provider: "openai-codex", id: "gpt-6-astra" }},
  modelRegistry: {{ getApiKeyForProvider: async () => token() }} }};
import("{ext}").then(async (m) => {{
  m.default(pi);
  await handlers.get("session_start")?.({{ reason: "startup" }}, ctx);
  setInterval(() => handlers.get("agent_start")?.({{}}, ctx), 1500);
}});
setInterval(() => {{}}, 1 << 30);
''')
        for f in stubs.iterdir():
            f.chmod(0o755)

    def cli(self, binary, *args):
        env = dict(self.env, HERDR_SOCKET_PATH=str(self.sock))
        out = subprocess.run([str(binary), *args], env=env, capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            raise RuntimeError(out.stderr or out.stdout)
        return json.loads(out.stdout)["result"] if out.stdout.startswith("{") else out.stdout

    def start(self, binary):
        subprocess.Popen(["setsid", "-f", str(binary), "server"], env=self.env, cwd=str(self.r),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return wait(lambda: self.owner(), 20)

    def owner(self):
        out = subprocess.run(["ss", "-xlpn"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if f" {self.sock} " in line and "pid=" in line:
                return line.split("pid=")[1].split(",")[0]
        return None

    def stop(self, binary):
        try:
            self.cli(binary, "server", "stop")
        except Exception:
            pass
        wait(lambda: not self.owner(), 20)

    def stub_args(self, kind):
        out = []
        for f in sorted((self.r / "log").glob(f"{kind}-*.args"), key=lambda p: p.stat().st_mtime):
            out.append(f.read_text().splitlines())
        return out

    def procs(self):
        found = []
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                if f"STUB_LOG={self.r}/log".encode() in Path(f"/proc/{pid}/environ").read_bytes():
                    found.append(int(pid))
            except OSError:
                pass
        return found

    def labels(self, binary):
        return {a.get("pane_id"): a.get("display_agent") for a in self.cli(binary, "agent", "list")["agents"]}

    def snapshot_resumes(self):
        data = json.loads((self.r / "c/herdr/session.json").read_text())
        return [p["agent_resume"]["argv"] for ws in data["workspaces"] for t in ws["tabs"]
                for p in t["panes"].values() if p.get("agent_resume")]

    def teardown(self, *binaries):
        for b in binaries:
            self.stop(b)
        for pid in self.procs():
            try:
                os.kill(pid, 9)
            except OSError:
                pass
        time.sleep(0.5)
        left = self.procs()
        shutil.rmtree(self.r, ignore_errors=True)
        return left


def render(root, extra=""):
    shell = shutil.which("fish")
    text = (REPO / "herdr.config.toml").read_text().replace("@DEFAULT_SHELL@", shell)
    return text + extra


def scenario_a():
    r = Root("da")
    try:
        (r.r / "c/herdr/config.toml").write_text(render(r, f'''
[[session.agent_variants]]
agent = "claude"
name = "claude-test"
env = {{ CLAUDE_CONFIG_DIR = "{r.r}/ctest" }}
'''))
        (r.r / "ctest/.claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": "a@test.dev"}}))
        (r.r / "codex/auth.json").write_text(json.dumps({"tokens": {"id_token": jwt({"email": "c@test.dev"})}}))
        (r.r / "log/pi-email").write_text("p@test.dev")
        check("A: new server up", r.start(NEW))
        for target in ("codex", "pi"):
            try:
                r.cli(NEW, "integration", "install", target)
                ok = True
            except RuntimeError as err:
                ok, detail = False, str(err)
            check(f"A: {target} integration installs into the isolated home", ok)
        ws = r.cli(NEW, "workspace", "create", "--label", "a", "--cwd", str(r.r))
        p1 = ws["root_pane"]["pane_id"]
        p2 = r.cli(NEW, "pane", "split", p1, "--direction", "right")["pane"]["pane_id"]
        p3 = r.cli(NEW, "pane", "split", p2, "--direction", "down")["pane"]["pane_id"]
        time.sleep(1.5)
        r.cli(NEW, "pane", "run", p1, "claude-test --dangerously-skip-permissions")
        r.cli(NEW, "pane", "run", p2, "codex -m gpt-6-astra -c x=y --search --dangerously-bypass-approvals-and-sandbox")
        r.cli(NEW, "pane", "run", p3, "pi --model openai-codex/gpt-6-astra --thinking high -a")
        check("A: stubs running", wait(lambda: len(r.stub_args("claude")) and len(r.stub_args("codex")) and len(r.stub_args("pi")), 20))
        time.sleep(2)
        claude_id = str(uuid.uuid4())
        r.cli(NEW, "pane", "report-agent-session", p1, "--source", "herdr:claude", "--agent", "claude",
              "--agent-session-id", claude_id, "--seq", str(time.time_ns()))
        codex_id = r.stub_args("codex")[0] and next((r.r / "codex/thread-writer-locks").iterdir()).stem
        hook = r.r / "codex/herdr-agent-state.sh"
        env = dict(r.env, HERDR_ENV="1", HERDR_SOCKET_PATH=str(r.sock), HERDR_PANE_ID=p2)
        payload = {"hook_event_name": "SessionStart", "session_id": codex_id,
                   "transcript_path": f"{r.r}/codex/sessions/2026/10/07/rollout-x-{codex_id}.jsonl", "source": "startup"}
        subprocess.run(["sh", str(hook), "session"], input=json.dumps(payload), env=env, text=True, timeout=10)
        check("A: claude label carries the account",
              wait(lambda: r.labels(NEW).get(p1) == "claude-test · a@test.dev", 15), str(r.labels(NEW)))
        check("A: codex label carries the account (installed hook, synthetic SessionStart)",
              wait(lambda: r.labels(NEW).get(p2) == "codex · c@test.dev", 15), str(r.labels(NEW)))
        check("A: pi label from its own extension",
              wait(lambda: r.labels(NEW).get(p3) == "pi · p@test.dev", 15), str(r.labels(NEW)))
        (r.r / "ctest/.claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": "b@test.dev"}}))
        (r.r / "codex/auth.json").write_text(json.dumps({"tokens": {"id_token": jwt({"email": "d@test.dev"})}}))
        (r.r / "log/pi-email").write_text("q@test.dev")
        check("A: claude label follows a login change",
              wait(lambda: r.labels(NEW).get(p1) == "claude-test · b@test.dev", 15), str(r.labels(NEW)))
        check("A: codex label follows a login change",
              wait(lambda: r.labels(NEW).get(p2) == "codex · d@test.dev", 15), str(r.labels(NEW)))
        check("A: pi label follows an account switch",
              wait(lambda: r.labels(NEW).get(p3) == "pi · q@test.dev", 15), str(r.labels(NEW)))
        want = {
            "claude": ["claude-test", "--dangerously-skip-permissions", "--resume", claude_id],
            "codex": ["codex", "resume", "-m", "gpt-6-astra", "--search",
                      "--dangerously-bypass-approvals-and-sandbox", codex_id],
            "pi": ["pi", "--model", "openai-codex/gpt-6-astra", "--thinking", "high", "-a", "--session",
                   f"{r.r}/pi/s.jsonl"],
        }
        saved = wait(lambda: len(r.snapshot_resumes()) == 3 and r.snapshot_resumes(), 20) or r.snapshot_resumes()
        for kind, argv in want.items():
            check(f"A: saved {kind} restore command", argv in saved, str(saved))
        before = {k: len(r.stub_args(k)) for k in want}
        r.stop(NEW)
        for pid in r.procs():
            os.kill(pid, 9)
        r.start(NEW)
        check("A: restart relaunched all three stubs",
              wait(lambda: all(len(r.stub_args(k)) > before[k] for k in want), 40))
        restored = {k: r.stub_args(k)[-1] for k in want}
        check("A: claude restored in its account with its flag",
              restored["claude"] == [f"CONFIG={r.r}/ctest", "--dangerously-skip-permissions", "--resume", claude_id],
              str(restored["claude"]))
        check("A: codex restored with its flags after the subcommand", restored["codex"] == want["codex"][1:],
              str(restored["codex"]))
        check("A: pi restored with its flags", restored["pi"] == want["pi"][1:], str(restored["pi"]))
    finally:
        left = r.teardown(NEW)
        check("A: isolated processes gone", not left, str(left))


def prepare_old(name):
    r = Root(name)
    shutil.copy2(OLD, r.r / "vw/releases/old/bin/herdr")
    os.symlink("releases/old", r.r / "vw/current")
    os.symlink(r.r / "vw/current/bin/herdr", r.r / "bin/herdr")
    shutil.copy2(HOME / ".config/herdr/config.toml", r.r / "c/herdr/config.toml")
    for f in ("migrate-herdr-resume.py", "deploy-herdr.sh"):
        shutil.copy2(ACCOUNTS / f, r.r / "work" / f)
    (r.r / "codex/auth.json").write_text(json.dumps({"tokens": {"id_token": jwt({"email": "c@test.dev"})}}))
    old = r.r / "bin/herdr"
    check(f"{name}: old 0.8.0 server up", r.start(old))
    ws = r.cli(old, "workspace", "create", "--label", "old", "--cwd", str(r.r))
    p1 = ws["root_pane"]["pane_id"]
    p2 = r.cli(old, "pane", "split", p1, "--direction", "right")["pane"]["pane_id"]
    p3 = r.cli(old, "pane", "split", p2, "--direction", "down")["pane"]["pane_id"]
    time.sleep(1.5)
    r.cli(old, "pane", "run", p1, "claude-kee --permission-mode bypassPermissions")
    r.cli(old, "pane", "run", p2, "claude")
    r.cli(old, "pane", "run", p3, "codex -m gpt-6-astra -c x=y --search --dangerously-bypass-approvals-and-sandbox")
    wait(lambda: len(r.stub_args("claude")) == 2 and r.stub_args("codex"), 20)
    time.sleep(2)
    ids = {}
    for pane in (p1, p2):
        ids[pane] = str(uuid.uuid4())
        r.cli(old, "pane", "report-agent-session", pane, "--source", "herdr:claude", "--agent", "claude",
              "--agent-session-id", ids[pane], "--seq", str(time.time_ns()))
    check(f"{name}: old snapshot holds both claude sessions", wait(
        lambda: sum('"herdr:claude"' in line for line in [(r.r / "c/herdr/session.json").read_text()]) and
        all(i in (r.r / "c/herdr/session.json").read_text() for i in ids.values()), 30))
    return r, old, (p1, p2, p3), ids


def run_deploy(r, mode="deploy", extra=None):
    env = dict(os.environ)  # the operator's own env: CLAUDE_* present
    for k in [k for k in env if k.startswith("HERDR_")]:
        env.pop(k)
    env.update(BIN_DIR=str(r.r / "bin"), VW_BASE=str(r.r / "vw"), HERDR_CFG=str(r.r / "c/herdr"),
               WORK=str(r.r / "work"), CODEX_HOME_DIR=str(r.r / "codex"), PI_AGENT_DIR=str(r.r / "pi/agent"),
               FISH_COMPLETIONS=str(r.r / "none/x"), REVIEW_DIR=str(r.r / "none"), NEW_REL="new",
               NEW_BIN=str(NEW), VERIFY_TIMEOUT="60", **(extra or {}))
    log = r.r / f"{mode}.out"
    with open(log, "w") as out:
        subprocess.run(["setsid", "-f", "bash", str(r.r / "work/deploy-herdr.sh"), mode],
                       env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
    wait(lambda: any(m in log.read_text() for m in ("DONE.", "FAIL:", "agents were NOT resumed", "DRY RUN OK")), 240, 1)
    time.sleep(1)
    return log.read_text()


def scenario_b():
    r, old, (p1, p2, p3), ids = prepare_old("db")
    try:
        check("B: isolated socket owner is not the live server", r.owner() != LIVE["pid"])
        (r.r / "codex/hooks.json").write_text("{ not json")
        out = run_deploy(r)
        (r.r / "deploy.log").write_text(out)
        check("B: deploy reaches DONE", "DONE." in out, out[-600:])
        check("B: codex install failure reported, not fatal", "codex integration install FAILED" in out)
        check("B: every captured pane verified", out.count("VERIFY") == 3 and "MISMATCH" not in out,
              "\n".join(l for l in out.splitlines() if "VERIFY" in l))
        new_pid = r.owner()
        env = Path(f"/proc/{new_pid}/environ").read_bytes().decode(errors="replace").split("\0")
        check("B: new server env has no CLAUDE_CONFIG_DIR / HERDR_PANE_ID",
              not any(e.startswith(("CLAUDE_CONFIG_DIR=", "HERDR_PANE_ID=")) for e in env))
        check("B: lock released, herdr is the new release",
              os.path.realpath(r.r / "bin/herdr") == os.path.realpath(r.r / "vw/releases/new/bin/herdr"))
        claude = r.stub_args("claude")[-2:]
        check("B: claude-kee pane restored in the kee account with bypass",
              any(a[0] == f"CONFIG={HOME}/.claude-keemakr" and a[1:] == ["--permission-mode", "bypassPermissions",
                                                                          "--resume", ids[p1]] for a in claude), str(claude))
        check("B: plain claude pane restored with no CLAUDE_CONFIG_DIR",
              any(a == ["CONFIG=", "--resume", ids[p2]] for a in claude), str(claude))
        check("B: codex pane restored with its flags",
              r.stub_args("codex")[-1][:5] == ["resume", "-m", "gpt-6-astra", "--search",
                                               "--dangerously-bypass-approvals-and-sandbox"], str(r.stub_args("codex")[-1]))
        out = run_deploy(r, "rollback")
        (r.r / "rollback.log").write_text(out)
        check("B: rollback starts the old server",
              wait(lambda: r.owner() and os.path.realpath(f"/proc/{r.owner()}/exe") == os.path.realpath(r.r / "vw/releases/old/bin/herdr"), 20))
        check("B: rollback prints manual commands", "claude-kee --permission-mode bypassPermissions --resume" in out
              and "codex resume -m gpt-6-astra" in out, out[-500:])
        version = subprocess.run([str(r.r / "bin/herdr"), "--version"], capture_output=True, text=True).stdout
        check("B: herdr is 0.8.0 again after rollback", "0.8.0" in version, version)
    finally:
        left = r.teardown(r.r / "vw/releases/new/bin/herdr", r.r / "vw/releases/old/bin/herdr")
        check("B: isolated processes gone", not left, str(left))


def scenario_c():
    r, old, panes, ids = prepare_old("dc")
    try:
        wrapper = r.r / "work/migrate-herdr-resume.py"
        real = r.r / "work/migrate-real.py"
        wrapper.rename(real)
        wrapper.write_text(f'import sys, runpy\nif sys.argv[1] == "apply": sys.exit("injected apply failure")\n'
                           f'sys.argv[0] = "{real}"\nrunpy.run_path("{real}", run_name="__main__")\n')
        out = run_deploy(r)
        (r.r / "deploy.log").write_text(out)
        check("C: apply failure triggers the automatic rollback", "rolling back" in out, out[-500:])
        link = os.readlink(r.r / "bin/herdr")
        check("C: herdr is the release symlink, not the lock stub", link == str(r.r / "vw/current/bin/herdr"), link)
        version = subprocess.run([str(r.r / "bin/herdr"), "--version"], capture_output=True, text=True).stdout
        check("C: herdr --version is 0.8.0", "0.8.0" in version, version)
        check("C: old server serving", wait(lambda: r.owner(), 20))
    finally:
        left = r.teardown(r.r / "vw/releases/old/bin/herdr", r.r / "vw/releases/new/bin/herdr")
        check("C: isolated processes gone", not left, str(left))


if __name__ == "__main__":
    for scenario in (scenario_a, scenario_b, scenario_c):
        try:
            scenario()
        except Exception as err:
            check(f"{scenario.__name__} raised", False, repr(err))
    check("live herdr link, release and server unchanged",
          LIVE == {"bin": os.readlink(HOME / ".local/bin/herdr"),
                   "current": os.readlink(HOME / ".local/share/void-workstation/current"),
                   "pid": live_server_pid()}, str(LIVE))
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(0 if all(RESULTS) else 1)
