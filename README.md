# 🎧 DJ Crate Digger

**Your AI agent organises your DJ library like a pro.** It reads tags, detects BPM and musical key, converts keys to **Camelot**, works out the sub-genre and energy, then renames and sorts every track.

Works with **Claude, OpenAI Codex / ChatGPT, Mistral (Vibe & API), Gemini CLI, Cursor, Copilot, OpenCode, Ollama / LM Studio**. Anything that speaks [Agent Skills](https://agentskills.io), [MCP](https://modelcontextprotocol.io) or an OpenAI-compatible API can use it.

```
before:  Downloads/01 - Artist - Night Drive (Original Mix).mp3
after:   DJ Library/01_By_Genre/House/Deep_House/124 - 8A - Artist - Night Drive (Original Mix).mp3
```

[![tests](https://github.com/eroldmc/dj-crate-digger/actions/workflows/tests.yml/badge.svg)](https://github.com/eroldmc/dj-crate-digger/actions)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.9%2B-blue)

---

## ✨ What it does

| Agent | Role |
|---|---|
| 🧭 **Supervisor** | your AI runs the pipeline and shows you a preview before touching any file |
| 🔍 **Digger** | reads tags (MP3, WAV, FLAC, AIFF, M4A, OGG); detects BPM and key from the audio when tags are missing |
| 🎡 **Harmonic Control** | converts every key to Camelot (`Am` → `8A`, `F#m` → `11A`, Open Key `1m` → `8A`) |
| 🎼 **Musicologist** | the LLM assigns genre, sub-genre (Deep House, Melodic Techno, Peak Time…) and energy (Warm Up → After) |
| 🗂️ **Archivist** | renames to `BPM - Key - Artist - Title`, sorts, builds playlists, can write tags back |

### The library you get

```
DJ Library/
├── 01_By_Genre/
│   ├── House/Deep_House/        124 - 8A - Artist - Title.mp3
│   ├── House/Tech_House/
│   ├── Techno/Peak_Time/
│   └── To_Sort/                 ← tracks with an uncertain genre
├── 02_By_Energy/                ← .m3u8 playlists, no duplicate files
│   ├── 1_Warm_Up.m3u8
│   ├── 2_Building.m3u8
│   ├── 3_Peak_Time.m3u8
│   ├── 4_Closing.m3u8
│   └── 5_After.m3u8
└── 03_New_This_Month/
    └── 2026-11_November.m3u8
```

The `.m3u8` playlists import straight into **Rekordbox, Serato, Traktor, Engine DJ and VirtualDJ**. Want French folder names? Add `--lang fr`.

### Your files are safe
- **Copy by default**: your originals stay where they are (`--move` only if you ask).
- **Preview first** (`--dry-run`) before anything is organised.
- **Safe to re-run**: a track that is already organised is never duplicated.

---

## 📦 Install

**Requirements:** Python 3.9+ and [ffmpeg](https://ffmpeg.org/download.html) (`brew install ffmpeg` · `sudo apt install ffmpeg` · `winget install ffmpeg`).

### Pick your agent

| Agent | Install |
|---|---|
| **Claude Code** | `/plugin marketplace add YOUR-USERNAME/dj-crate-digger` then `/plugin install dj-crate-digger@dj-crate-digger` |
| **Claude.ai** (web/desktop) | download `dj-crate-digger.zip` from [Releases](https://github.com/YOUR-USERNAME/dj-crate-digger/releases) → *Customize > Skills > + > Upload a skill* |
| **OpenAI Codex** | `python3 install.py --agent agents` (installs to `~/.agents/skills`) |
| **Mistral Vibe** | `python3 install.py --agent agents` (Vibe reads `~/.agents/skills`) |
| **Gemini CLI** | `gemini skills install https://github.com/YOUR-USERNAME/dj-crate-digger --path skills` |
| **Cursor, OpenCode, Cline, Windsurf, 40+ others** | `npx skills add YOUR-USERNAME/dj-crate-digger` |
| **ChatGPT desktop, Claude Desktop, LM Studio, VS Code…** | add the MCP server, see [docs/mcp.md](docs/mcp.md) |
| **Any LLM API** (OpenAI, Mistral, Gemini, Ollama…) | use the CLI, see [Without an agent](#-without-an-agent-any-llm-api) |

### Or the all-in-one installer
```bash
git clone https://github.com/YOUR-USERNAME/dj-crate-digger.git
cd dj-crate-digger
python3 install.py --deps        # ~/.agents/skills + ~/.claude/skills, plus Python dependencies
```
`install.py --agent claude agents codex gemini vibe opencode` picks the targets, `--project` installs into the current project, and `--uninstall` removes the skill.

---

## 🚀 Use it with your agent

Just ask:

> "Organise my DJ library: take `~/Music/Promos` and sort it into `~/Music/DJ Library`."

> "Analyse this folder and tell me which tracks are Peak Time in 8A or 9A."

> "Suggest a harmonic set order from my Warm Up playlist."

The agent analyses the tracks, shows you a summary table, waits for your OK, then organises everything.

## 🔌 MCP server

For apps that use MCP tools instead of skills (ChatGPT desktop, Claude Desktop, Cursor, Codex, Gemini CLI, Mistral Vibe, LM Studio…):

```
uvx --from git+https://github.com/YOUR-USERNAME/dj-crate-digger --with mcp --with librosa --with soundfile crate-digger-mcp
```

Ready-to-paste config for each app: **[docs/mcp.md](docs/mcp.md)**.

## 🛠️ Without an agent (any LLM API)

```bash
pip install "dj-crate-digger[audio] @ git+https://github.com/YOUR-USERNAME/dj-crate-digger"

# 1. Analyse: tags + BPM + Camelot key + energy score
crate-digger analyze ~/Music/Promos --out plan.json

# 2. Classify genre / sub-genre / energy with the LLM of your choice
export MISTRAL_API_KEY=...
crate-digger classify plan.json --provider mistral --model mistral-small-latest

# 3. Preview, then organise
crate-digger apply plan.json --library "~/Music/DJ Library" --dry-run
crate-digger apply plan.json --library "~/Music/DJ Library" --write-tags
```

Built-in providers for `classify` (the API key is read from the matching environment variable):

| `--provider` | Key variable | Notes |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | |
| `mistral` | `MISTRAL_API_KEY` | |
| `anthropic` | `ANTHROPIC_API_KEY` | OpenAI-compatible endpoint |
| `gemini` | `GEMINI_API_KEY` | OpenAI-compatible endpoint |
| `openrouter` | `OPENROUTER_API_KEY` | hundreds of models |
| `groq` | `GROQ_API_KEY` | |
| `deepseek` | `DEEPSEEK_API_KEY` | |
| `ollama` | none | 100% local and free, e.g. `--model llama3.1` |
| `lmstudio` | none | 100% local |

Any other OpenAI-compatible server works too: `--base-url https://…/v1 --api-key …`.
You can also skip `classify` and fill `genre`, `sub_genre` and `energy` in `plan.json` yourself (see [examples/plan.example.json](examples/plan.example.json)).

| Command / option | Effect |
|---|---|
| `analyze --no-audio` | tags only, no audio analysis (instant) |
| `classify --force` | re-classify tracks that already have a genre |
| `apply --dry-run` | show the plan, copy nothing |
| `apply --write-tags` | write BPM + Camelot key into the organised files (MP3/FLAC/OGG) |
| `apply --move` | move instead of copy |
| `apply --lang fr` | French folder names |
| `camelot Am F#m 1m` | convert keys and list compatible keys for mixing |

Energy values: `warm_up`, `building`, `peak_time`, `closing`, `after`.

---

## ⚠️ Known limits
- **BPM detected from audio** is approximate (±3 BPM); existing tags always take priority.
- **Key detection** (Krumhansl profiles) is reliable on tonal music, less so on very percussive techno. Check tracks marked `key_source: audio`.
- No acoustic fingerprinting (Shazam/AcoustID) yet: a track without tags is identified from its file name.
- Tags are written back for MP3, FLAC and OGG only.
- Web-only chat apps can't reach files on your computer. Use a desktop app (MCP), a CLI agent or the `classify` command.

## 🗺️ Roadmap
- [ ] AcoustID identification for untagged files
- [ ] Rekordbox XML export
- [ ] Automatic harmonic set builder (Camelot ±1 + rising BPM)

## 🗂️ Repository layout
```
skills/dj-crate-digger/          ← the skill (Agent Skills standard), self-contained
├── SKILL.md
└── scripts/
    ├── crate_digger.py          ← CLI + core logic
    └── crate_digger_mcp.py      ← MCP server
AGENTS.md                        ← instructions for coding agents working in this repo
.claude-plugin/                  ← Claude Code plugin + marketplace
docs/mcp.md                      ← MCP setup per app
install.py                       ← cross-agent installer
pyproject.toml                   ← pip / uvx package (crate-digger, crate-digger-mcp)
```

## 🧪 Tests
```bash
pip install mutagen mcp pytest
pytest -q
```

## 🤝 Contributing
Issues and pull requests are welcome: new sub-genres, file formats, DJ software exports, translations (`LABELS` in `crate_digger.py`).

## 📄 License
[MIT](LICENSE)
