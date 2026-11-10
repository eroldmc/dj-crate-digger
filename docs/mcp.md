# MCP server: use DJ Crate Digger from any AI app

The MCP server gives your AI app four tools. The app's own model (GPT, Claude, Mistral, Gemini, Llama…) does the genre classification, so you don't need a separate API key.

| Tool | What it does |
|---|---|
| `analyze_music_folder` | scans a folder: reuses Serato/Rekordbox analysis and playlists, then tags, BPM, Camelot key, energy score |
| `classify_tracks` | saves the genre / sub-genre / energy that the model chose |
| `organize_library` | preview (`dry_run`) or run the renaming and sorting |
| `camelot_keys` | converts keys to Camelot and lists compatible keys |

## The launch command

With [uv](https://docs.astral.sh/uv/) you don't have to install anything else. Every client below uses this command:

```
uvx --from git+https://github.com/eroldmc/dj-crate-digger --with mcp --with librosa --with soundfile crate-digger-mcp
```

Without uv, run `pip install "dj-crate-digger[all] @ git+https://github.com/eroldmc/dj-crate-digger"` once, then use `crate-digger-mcp` as the command.

> Analysing a big folder can take several minutes. Raise the client's tool timeout if it has one.

## Claude Desktop / Claude Code
`claude_desktop_config.json` (Settings → Developer → Edit config):
```json
{
  "mcpServers": {
    "dj-crate-digger": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/eroldmc/dj-crate-digger",
               "--with", "mcp", "--with", "librosa", "--with", "soundfile", "crate-digger-mcp"]
    }
  }
}
```
Claude Code: `claude mcp add dj-crate-digger -- uvx --from git+https://github.com/eroldmc/dj-crate-digger --with mcp --with librosa --with soundfile crate-digger-mcp`

## OpenAI Codex (CLI, IDE extension, ChatGPT desktop app)
`~/.codex/config.toml`:
```toml
[mcp_servers.dj-crate-digger]
command = "uvx"
args = ["--from", "git+https://github.com/eroldmc/dj-crate-digger",
        "--with", "mcp", "--with", "librosa", "--with", "soundfile", "crate-digger-mcp"]
tool_timeout_sec = 600
```
In the ChatGPT desktop app: **Settings → MCP servers → Add server → STDIO**. Use the same command and arguments.

## Mistral Vibe
```bash
vibe mcp add dj-crate-digger --transport stdio --command uvx \
  --arg --from --arg git+https://github.com/eroldmc/dj-crate-digger \
  --arg --with --arg mcp --arg --with --arg librosa --arg --with --arg soundfile \
  --arg crate-digger-mcp
```
Or add this to `~/.vibe/config.toml`:
```toml
[[mcp_servers]]
name = "dj-crate-digger"
transport = "stdio"
command = "uvx"
args = ["--from", "git+https://github.com/eroldmc/dj-crate-digger",
        "--with", "mcp", "--with", "librosa", "--with", "soundfile", "crate-digger-mcp"]
```

## Gemini CLI
`~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "dj-crate-digger": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/eroldmc/dj-crate-digger",
               "--with", "mcp", "--with", "librosa", "--with", "soundfile", "crate-digger-mcp"],
      "timeout": 600000
    }
  }
}
```

## Cursor, VS Code (Copilot), LM Studio, Windsurf, Cline…
These apps take the same `mcpServers` JSON block as Claude Desktop:
- Cursor: `~/.cursor/mcp.json`
- LM Studio: Program → Edit `mcp.json` (works with local models)
- VS Code: `.vscode/mcp.json`. Here the top-level key is `"servers"` instead of `"mcpServers"`.

## Example prompt
> Analyse `~/Music/Promos`, classify every track, show me the plan, then organise it into `~/Music/DJ Library` and write the tags.
