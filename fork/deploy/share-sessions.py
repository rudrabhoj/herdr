#!/usr/bin/env python3
"""Share Claude Code session storage between config dirs, keep auth separate.

Claude Code derives every session path from CLAUDE_CONFIG_DIR (projects/ is
hard-wired to <config>/projects), so two config dirs can only resume each
other's sessions if they point at the same session stores. This merges each
member's stores into the canonical dir and replaces them with symlinks.
Credentials (.credentials.json) and the account file (.claude.json) are never
touched, so each dir keeps its own login.

The canonical dir keeps the physical stores so already-running sessions there
never see their directories move. Usage:
    share-sessions.py [--apply] CANONICAL MEMBER [MEMBER...]
"""
import filecmp
import os
import shutil
import sys
import time
from pathlib import Path

SHARED = ["projects", "file-history", "session-env", "tasks", "todos", "plans", "paste-cache"]


def merge_index(canonical: Path, incoming: Path, apply: bool):
    """Union of MEMORY.md lines; canonical order first, header kept once."""
    have = canonical.read_text().splitlines()
    extra = [line for line in incoming.read_text().splitlines()
             if line.strip() and line not in have and not line.startswith("# ")]
    if extra and apply:
        canonical.write_text("\n".join(have + extra) + "\n")
    return len(extra)


def merge_tree(src: Path, dst: Path, conflicts: Path, apply: bool, stats: dict):
    for entry in sorted(src.iterdir()):
        target = dst / entry.name
        if entry.is_dir() and not entry.is_symlink():
            if not target.exists():
                stats["moved"] += 1
                if apply:
                    dst.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(entry), str(target))
            else:
                merge_tree(entry, target, conflicts / entry.name, apply, stats)
            continue
        if not target.exists():
            stats["moved"] += 1
            if apply:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.move(str(entry), str(target))
        elif filecmp.cmp(entry, target, shallow=False):
            stats["identical"] += 1
        elif entry.name == "MEMORY.md":
            stats["index_lines"] += merge_index(target, entry, apply)
        else:
            stats["conflicts"].append(str(target))
            if apply:
                conflicts.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, conflicts / entry.name)


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    args = [a for a in args if a != "--apply"]
    canonical, members = Path(args[0]).expanduser(), [Path(a).expanduser() for a in args[1:]]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = Path.home() / ".local/share/claude-accounts" / f"merge-conflicts-{stamp}"
    for member in members:
        for name in SHARED:
            src, dst = member / name, canonical / name
            if src.is_symlink():
                ok = os.path.realpath(src) == os.path.realpath(dst)
                print(f"{src}: already linked{'' if ok else ' ELSEWHERE -> ' + os.readlink(src)}")
                continue
            stats = {"moved": 0, "identical": 0, "index_lines": 0, "conflicts": []}
            if src.is_dir():
                merge_tree(src, dst, archive / member.name / name, apply, stats)
            print(f"{src} -> {dst}: moved {stats['moved']}, identical {stats['identical']}, "
                  f"index lines merged {stats['index_lines']}, conflicts kept from canonical "
                  f"{len(stats['conflicts'])}")
            for path in stats["conflicts"]:
                print(f"    conflict (member copy archived): {path}")
            if apply:
                dst.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.rmtree(src)
                src.symlink_to(dst)
    print("applied" if apply else "dry run; pass --apply to change anything")


if __name__ == "__main__":
    main()
