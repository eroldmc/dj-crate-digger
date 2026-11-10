#!/usr/bin/env python3
"""Install the dj-crate-digger skill for your AI agents (macOS, Linux, Windows).

  python3 install.py                 # auto: ~/.agents/skills (Codex, Mistral Vibe, Gemini CLI...)
                                     #       + ~/.claude/skills if Claude Code is installed
  python3 install.py --agent codex claude
  python3 install.py --project       # install into the current project instead of your home
  python3 install.py --deps          # also pip install the Python dependencies
  python3 install.py --uninstall
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "dj-crate-digger"
SRC = Path(__file__).resolve().parent / "skills" / NAME
HOME = Path.home()

# agent -> skills directory, relative to the home (or project) root
TARGETS = {
    "agents": ".agents/skills",   # open standard: Codex, Mistral Vibe, Gemini CLI, and more
    "claude": ".claude/skills",   # Claude Code
    "codex": ".codex/skills",     # older Codex versions
    "gemini": ".gemini/skills",
    "vibe": ".vibe/skills",
    "opencode": ".config/opencode/skills",
}


def auto_targets(root):
    found = ["agents"]
    if (root / ".claude").exists():
        found.append("claude")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", nargs="+", choices=list(TARGETS) + ["all"], help="where to install")
    ap.add_argument("--project", action="store_true", help="install in ./ instead of your home folder")
    ap.add_argument("--deps", action="store_true", help="pip install mutagen, librosa, soundfile, mcp")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    root = Path.cwd() if args.project else HOME
    agents = list(TARGETS) if args.agent == ["all"] else (args.agent or auto_targets(root))
    for agent in agents:
        dest = root / TARGETS[agent] / NAME
        if args.uninstall:
            if dest.exists():
                shutil.rmtree(dest)
                print(f"removed   {dest}")
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"installed {agent:8} -> {dest}")

    if args.deps and not args.uninstall:
        cmd = [sys.executable, "-m", "pip", "install", "mutagen", "librosa", "soundfile", "mcp"]
        print("$", " ".join(cmd))
        subprocess.call(cmd)
    if not args.uninstall:
        print("\nDone. Restart your agent, then ask it: \"Organise my DJ library in ~/Music/Promos\".")
        if shutil.which("ffmpeg") is None:
            print("Note: ffmpeg not found - install it to analyse MP3/M4A files.")


if __name__ == "__main__":
    main()
