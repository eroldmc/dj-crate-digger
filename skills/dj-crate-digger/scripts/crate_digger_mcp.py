#!/usr/bin/env python3
"""DJ Crate Digger MCP server (stdio).

Exposes the pipeline to any MCP client (Claude Desktop, ChatGPT, Cursor, Codex, Gemini CLI,
Mistral Le Chat / Vibe, VS Code, LM Studio...). The client's own model acts as the
Musicologist: it reads the analysis and sends genres back with `classify_tracks`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crate_digger as cd  # noqa: E402

try:                                   # MCP Python SDK v2
    from mcp.server import MCPServer as _Server
except ImportError:                    # MCP Python SDK v1
    from mcp.server.fastmcp import FastMCP as _Server

INSTRUCTIONS = f"""Organise a DJ music library. Workflow:
1. analyze_music_folder -> per-track BPM, Camelot key, tags, energy_score.
2. YOU choose genre / sub_genre / energy for each track and call classify_tracks.
   Genres: {', '.join(cd.GENRES)}, To_Sort (when unsure). Energy: {', '.join(cd.ENERGY_LEVELS)}.
   Reference BPM: House 118-126, Tech House 124-128, Peak Time Techno 128-135, DnB 170-175.
3. organize_library with dry_run=true, show the plan to the user, wait for approval.
4. organize_library with dry_run=false. Files are copied unless the user asked to move them."""

mcp = _Server("dj-crate-digger", instructions=INSTRUCTIONS)

_SUMMARY_KEYS = ("artist", "title", "genre_tag", "label", "bpm", "bpm_source", "key", "key_source",
                 "energy_score", "duration_s", "warnings", "genre", "sub_genre", "energy")


@mcp.tool()
def analyze_music_folder(source: str, plan_path: str = "", audio_analysis: bool = True) -> str:
    """Scan a folder of audio files: read tags, detect BPM, musical key (Camelot) and energy.
    Writes a plan JSON (default: <source>/crate_digger_plan.json) and returns a compact summary."""
    plan_path = plan_path or str(Path(source).expanduser() / "crate_digger_plan.json")
    plan = cd.analyze_folder(source, plan_path, audio=audio_analysis)
    rows = [{"i": i, **{k: t[k] for k in _SUMMARY_KEYS if t.get(k) is not None}}
            for i, t in enumerate(plan["tracks"])]
    return json.dumps({"plan_path": plan_path, "count": len(rows), "tracks": rows}, ensure_ascii=False)


@mcp.tool()
def classify_tracks(plan_path: str, classifications: list[dict]) -> str:
    """Save genre classification into the plan. Each item: {"i": <track index>, "genre": str,
    "sub_genre": str, "energy": warm_up|building|peak_time|closing|after}. Optional "artist"/"title"
    to fix wrong metadata."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    n = 0
    for c in classifications:
        i = c.get("i")
        if not isinstance(i, int) or not 0 <= i < len(plan["tracks"]):
            continue
        t = plan["tracks"][i]
        for k in ("genre", "sub_genre", "artist", "title"):
            if c.get(k):
                t[k] = c[k]
        if c.get("energy") in cd.ENERGY_LEVELS:
            t["energy"] = c["energy"]
        n += 1
    Path(plan_path).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    missing = sum(1 for t in plan["tracks"] if not t.get("genre"))
    return json.dumps({"updated": n, "still_unclassified": missing})


@mcp.tool()
def organize_library(plan_path: str, library: str, dry_run: bool = True, move: bool = False,
                     write_tags: bool = False, lang: str = "en") -> str:
    """Rename files to 'BPM - Key - Artist - Title' and sort them into <library>/01_By_Genre/...,
    with energy and monthly .m3u8 playlists. ALWAYS call with dry_run=true first and get user
    approval. Copies by default; move=true moves originals. lang: 'en' or 'fr' folder names."""
    report = cd.apply_plan(plan_path, library, dry_run=dry_run, move=move, tags=write_tags, lang=lang)
    counts = {}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return json.dumps({"dry_run": dry_run, "counts": counts, "files": report}, ensure_ascii=False)


@mcp.tool()
def camelot_keys(keys: list[str]) -> str:
    """Convert musical keys (Am, F#m, Bbmaj, Open Key 1m...) to Camelot, with compatible mixes."""
    return json.dumps([{"key": k, "camelot": cd.to_camelot(k),
                        "compatible": cd.compatible_keys(cd.to_camelot(k))} for k in keys])


def main():
    mcp.run()


if __name__ == "__main__":
    main()
