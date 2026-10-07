#!/usr/bin/env python3
"""Headless end-to-end check of the fork's scoped modes against a real server.

Everything runs under a throwaway XDG root with every HERDR_* variable
stripped, so the live server, its sockets, config, and session are untouched.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pexpect
import pyte

HERDR, TEMPLATE = sys.argv[1], Path(sys.argv[2])
ROOT = Path("/tmp/claude-1000/he")  # short: unix socket paths are capped
COLS, ROWS = 160, 40
ENV = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
ENV.update(
    XDG_CONFIG_HOME=str(ROOT / "c"),
    XDG_DATA_HOME=str(ROOT / "d"),
    XDG_STATE_HOME=str(ROOT / "s"),
    XDG_CACHE_HOME=str(ROOT / "k"),
    TERM="xterm-256color",
    fish_history="",
)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def cli(*args):
    out = subprocess.run([HERDR, *args], env=ENV, capture_output=True, text=True, timeout=20)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)} failed: {out.stderr or out.stdout}")
    return json.loads(out.stdout)["result"] if out.stdout.startswith("{") else out.stdout


def tabs(ws):
    return cli("tab", "list", "--workspace", ws)["tabs"]


def tab_ids(ws):
    return [t["tab_id"] for t in tabs(ws)]


def focused_tab(ws):
    return next(t["tab_id"] for t in tabs(ws) if t["focused"])


def workspaces():
    return cli("workspace", "list")["workspaces"]


def ws_ids():
    return [w["workspace_id"] for w in workspaces()]


def focused_ws():
    return next(w["workspace_id"] for w in workspaces() if w["focused"])


def layout(pane):
    return cli("pane", "layout", "--pane", pane)["layout"]


def panes(tab):
    return [p for p in cli("pane", "list")["panes"] if p["tab_id"] == tab]


class TolerantScreen(pyte.Screen):
    # herdr probes the host with private CSI queries pyte does not model.
    def report_device_status(self, *args, **kwargs):
        pass

    def select_graphic_rendition(self, *attrs, private=False):
        if not private:
            super().select_graphic_rendition(*attrs)


class Client:
    def __init__(self):
        self.screen = TolerantScreen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.child = pexpect.spawn(HERDR, [], env=ENV, cwd=str(ROOT), encoding="utf-8",
                                   codec_errors="replace", timeout=20, dimensions=(ROWS, COLS))

    def pump(self, seconds=0.6):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                self.stream.feed(self.child.read_nonblocking(65536, timeout=0.1))
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                return False
        return True

    def send(self, data, settle=0.6):
        self.child.send(data)
        self.pump(settle)

    def text(self):
        return "\n".join(self.screen.display)

    def bar(self, badge):
        return next((line for line in self.screen.display if f" {badge} " in line), None)

    def wait_until(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.pump(0.3)
            try:
                if predicate():
                    return True
            except (RuntimeError, StopIteration, KeyError):
                pass
        return False


def render_config():
    fish = shutil.which("fish") or ""
    cfg = ROOT / "c/herdr/config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(TEMPLATE.read_text().replace("@DEFAULT_SHELL@", fish))
    out = subprocess.run([HERDR, "config", "check"], env=ENV, capture_output=True, text=True)
    check("fork config template passes `herdr config check`", out.returncode == 0,
          (out.stdout + out.stderr).strip())
    check("config check reports no diagnostics", "warn" not in (out.stdout + out.stderr).lower()
          and "unknown" not in (out.stdout + out.stderr).lower(), (out.stdout + out.stderr).strip())


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    render_config()

    c = Client()
    try:
        check("client starts an isolated server",
              c.wait_until(lambda: (ROOT / "c/herdr/herdr.sock").exists() and workspaces(), 20))
        ws1 = focused_ws()
        for _ in range(2):
            cli("tab", "create", "--workspace", ws1)
        ws2 = cli("workspace", "create", "--label", "two", "--cwd", str(ROOT))["workspace"]["workspace_id"]
        ws3 = cli("workspace", "create", "--label", "three", "--cwd", str(ROOT))["workspace"]["workspace_id"]
        cli("workspace", "focus", ws1)
        cli("tab", "focus", tab_ids(ws1)[0])
        t1, t2, t3 = tab_ids(ws1)
        c.pump(1.5)

        # --- TABS (ctrl+t) ---------------------------------------------------
        c.send("\x14")
        check("ctrl+t opens TABS bar", c.bar("TABS"), c.text()[-400:])
        c.send("l")
        check("tabs: l focuses next tab", c.wait_until(lambda: focused_tab(ws1) == t2))
        check("tabs: mode stays after navigation", c.bar("TABS"))
        c.send("1")
        check("tabs: 1 switches to first tab", c.wait_until(lambda: focused_tab(ws1) == t1))
        c.send("o")
        check("tabs: o moves tab right", c.wait_until(lambda: tab_ids(ws1) == [t2, t1, t3]))
        check("tabs: focus follows moved tab", focused_tab(ws1) == t1)
        c.send("i")
        check("tabs: i moves tab back left", c.wait_until(lambda: tab_ids(ws1) == [t1, t2, t3]))
        c.send("i", settle=1)
        check("tabs: i at first tab is a no-op (no wrap)", tab_ids(ws1) == [t1, t2, t3])
        check("tabs: mode stays after reorder", c.bar("TABS"))
        c.send("n")
        check("tabs: n creates a tab", c.wait_until(lambda: len(tab_ids(ws1)) == 4))
        check("tabs: n leaves the mode", c.wait_until(lambda: not c.bar("TABS")))
        t4 = tab_ids(ws1)[3]

        # esc / toggle-off / prefix chain
        c.send("\x14")
        c.send("\x1b", settle=1)
        check("esc exits the mode", not c.bar("TABS"))
        c.send("\x14")
        c.send("\x14")
        check("ctrl+t again toggles the mode off", not c.bar("TABS"))
        c.send("\x14")
        c.send("\x02")
        check("prefix key chains into PREFIX", c.bar("PREFIX") and not c.bar("TABS"))
        c.send("\x1b")

        # --- direct reorder bindings (alt+i / alt+o) --------------------------
        cli("tab", "focus", t1)
        c.pump(0.8)
        c.send("\x1bo")
        check("alt+o moves the tab right outside the mode",
              c.wait_until(lambda: tab_ids(ws1)[:2] == [t2, t1]))
        c.send("\x1bi")
        check("alt+i moves it back", c.wait_until(lambda: tab_ids(ws1)[:2] == [t1, t2]))

        # --- SPACES (ctrl+o) --------------------------------------------------
        c.send("\x0f")
        check("ctrl+o opens SPACES bar", c.bar("SPACES"), c.text()[-400:])
        c.send("j")
        check("spaces: j focuses next workspace", c.wait_until(lambda: focused_ws() == ws2))
        c.send("o")
        check("spaces: o moves workspace down", c.wait_until(lambda: ws_ids() == [ws1, ws3, ws2]))
        c.send("o", settle=1)
        check("spaces: o at bottom is a no-op", ws_ids() == [ws1, ws3, ws2])
        c.send("i")
        check("spaces: i moves workspace up", c.wait_until(lambda: ws_ids() == [ws1, ws2, ws3]))
        c.send("k")
        check("spaces: k focuses previous workspace", c.wait_until(lambda: focused_ws() == ws1))
        check("spaces: mode stays", c.bar("SPACES"))
        before = (focused_ws(), focused_tab(ws1))
        c.send("h", settle=1)
        c.send("l", settle=1)
        check("spaces: off-axis h/l are inert",
              (focused_ws(), focused_tab(ws1)) == before and c.bar("SPACES"))
        c.send("t")
        check("t switches scope to TABS in place", c.bar("TABS") and not c.bar("SPACES"))
        c.send("a")
        check("a switches scope to AGENTS", c.bar("AGENTS"))
        count = len(tab_ids(ws1))
        c.send("n", settle=1)
        check("agents: n is inert", len(tab_ids(ws1)) == count and c.bar("AGENTS"))
        c.send("\x1b")

        # --- AGENTS (ctrl+g) --------------------------------------------------
        c.send("\x07")
        check("ctrl+g opens AGENTS bar", c.bar("AGENTS"))
        c.send("\x1b")

        # --- PANES (ctrl+p) ---------------------------------------------------
        tab = focused_tab(ws1)
        c.send("\x10")
        bar = c.bar("PANES")
        check("ctrl+p opens PANES bar", bar, c.text()[-400:])
        check("panes bar hides 1-9 and shows zoom", bar and "1-9" not in bar and "zoom" in bar, bar or "")
        c.send("n")
        check("panes: n splits the focused pane", c.wait_until(lambda: len(panes(tab)) == 2))
        check("panes: split leaves the mode", c.wait_until(lambda: not c.bar("PANES")))
        split = layout(panes(tab)[0]["pane_id"])["splits"]
        check("panes: wide pane auto-splits right", [x["direction"] for x in split] == ["right"], str(split))
        focused_after_split = next(p["pane_id"] for p in panes(tab) if p["focused"])
        c.send("\x10")
        c.send("h")
        check("panes: h moves focus left",
              c.wait_until(lambda: next(p["pane_id"] for p in panes(tab) if p["focused"]) != focused_after_split))
        check("panes: mode stays after focus", c.bar("PANES"))
        pane = panes(tab)[0]["pane_id"]
        c.send("z")
        check("panes: z zooms", c.wait_until(lambda: layout(pane)["zoomed"]))
        check("panes: z keeps the mode", c.bar("PANES"))
        c.send("z")
        check("panes: z again unzooms", c.wait_until(lambda: not layout(pane)["zoomed"]))
        c.send("x")
        check("panes: x closes the pane", c.wait_until(lambda: len(panes(tab)) == 1))
        c.send("\x1b")

        # --- help overlay lists the modes --------------------------------------
        c.send("\x02")
        c.send("?", settle=1)
        check("help overlay opens", "keybinds" in c.text().lower())
        c.send("\x1b")

        # --- detach / reattach keeps the reordered state ----------------------
        cli("tab", "focus", t1)
        c.pump(0.5)
        c.send("\x1bo")
        c.wait_until(lambda: tab_ids(ws1)[:2] == [t2, t1])
        order = tab_ids(ws1)
        c.send("\x02")
        c.send("d", settle=0.5)
        try:
            c.child.expect(pexpect.EOF, timeout=10)
            detached = True
        except pexpect.TIMEOUT:
            detached = False
        check("prefix+d detaches the client", detached)
    finally:
        c.child.close(force=True)

    r = Client()
    try:
        r.pump(2)
        check("reattach sees the reordered tabs", tab_ids(ws1) == order)
        r.send("\x14")
        check("modes work after reattach", r.bar("TABS"))
        r.send("\x1b")
    finally:
        r.child.close(force=True)

    subprocess.run([HERDR, "server", "stop"], env=ENV, capture_output=True, timeout=20)
    time.sleep(1)
    leftover = subprocess.run(["pgrep", "-f", str(ROOT)], capture_output=True, text=True).stdout.split()
    check("isolated server and panes shut down", not leftover, " ".join(leftover))

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if not failed:
        shutil.rmtree(ROOT, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
