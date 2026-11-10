# AGENTS.md

Instructions for AI coding agents (Codex, Mistral Vibe, Gemini CLI, Cursor, Copilot, OpenCode, Claude Code...) working in this repository.

## Using the tool
If the user asks to organise, sort, rename or analyse DJ music / audio files, follow
[`skills/dj-crate-digger/SKILL.md`](skills/dj-crate-digger/SKILL.md) step by step. The script is
`skills/dj-crate-digger/scripts/crate_digger.py`. Always preview with `--dry-run` and get approval
before copying or moving files.

## Developing
- Core logic: `skills/dj-crate-digger/scripts/crate_digger.py` (standard library + mutagen; librosa optional)
- MCP server: `skills/dj-crate-digger/scripts/crate_digger_mcp.py`
- Keep the skill folder self-contained: everything it needs lives under `skills/dj-crate-digger/`.
- Tests: `pip install mutagen pytest && pytest -q`. Add a test for every behaviour change.
- User-facing text in English. Folder names are translated through `LABELS` (`--lang`).
