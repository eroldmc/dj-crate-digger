---
name: dj-crate-digger
description: Organise a DJ music library (MP3/WAV/FLAC/AIFF/M4A) - reuse Serato/Rekordbox analysis, detect BPM and Camelot key, classify genre and energy, rename and sort tracks.
license: MIT
compatibility: Needs Python 3.10+, local file access and a shell. ffmpeg required for MP3/M4A analysis.
---

# DJ Crate Digger

You are organising a DJ library. The work is split between a bundled script and you:

| Role | Done by | Output |
|---|---|---|
| Supervisor | **you** | run the steps, show a preview, never touch files without approval |
| Digger | `scripts/crate_digger.py analyze` | tags + BPM/key/energy detected from audio |
| Harmonic Control | `scripts/crate_digger.py analyze` | key in Camelot notation (8A, 11B...), BPM folded to 85-175 |
| Musicologist | **you** | `genre`, `sub_genre`, `energy` for every track in `plan.json` |
| Archivist | `scripts/crate_digger.py apply` | `BPM - Key - Artist - Title.ext`, folders, playlists |

`scripts/` is relative to this skill's folder. Use the script as is; do not rewrite it.
In the commands below, `$S` stands for the full path to `scripts/crate_digger.py`.

## 1. Setup
```bash
python3 -m pip install mutagen librosa soundfile    # add --break-system-packages if pip asks
```
`ffmpeg` must be installed to read MP3/M4A (`brew install ffmpeg` / `sudo apt install ffmpeg` / `winget install ffmpeg`).
If librosa can't be installed, the script falls back to tags only.

## 2. Analyse (Digger + Harmonic Control)
```bash
python3 $S analyze "<source folder>" --out plan.json
```
About 3-6 s per track (90 s analysed from the middle). `--no-audio` = tags only, instant.
**Serato / Rekordbox users:** the script reuses their BPM, key, edited metadata and crates/playlists, and
tracks they already analysed skip the audio analysis entirely.
- Serato: the `_Serato_` folder is found automatically (`~/Music` and the root of the music drive). Ask the user to quit Serato first.
- Rekordbox: needs a collection XML (Rekordbox: **File → Export Collection in xml format**). The latest export in
  the source folder, Music, Documents, Desktop or Downloads is found automatically, or pass `--rekordbox <file.xml>`.
  If the user uses Rekordbox and no XML is found, tell them how to export it.
- `--serato off|PATH`, `--rekordbox off|PATH`, `--force-audio` (re-analyse anyway, gives an `energy_score`).
Priority: Serato > Rekordbox > file tags > audio detection; disagreements are listed in `warnings`.
Audio BPM is approximate (±3): flag tracks with `bpm_source: "audio"`.
Tracks without tags are identified from their file name: flag them "to check".

## 3. Classify (Musicologist - you)
For each track in `plan.json`, set:
- `genre`: House, Techno, Trance, Drum_and_Bass, Bass, Disco, Downtempo, Hip-Hop, Pop - or `To_Sort` when unsure
- `sub_genre`: precise - Deep House, Tech House, Organic House, Afro House, Melodic Techno, Peak Time, Hard Techno, Minimal, Progressive, Liquid, Nu Disco, Indie Dance...
- `energy`: `warm_up` | `building` | `peak_time` | `closing` | `after`

Clues, most reliable first: `serato_playlists` / `rekordbox_playlists` (the DJ's own crates and playlists), `genre_tag`, artist/label/title you actually know, `bpm`, `energy_score` (1-10), key.
Reference BPM: House 118-126, Tech House 124-128, Melodic Techno 120-126, Peak Time Techno 128-135, Hard Techno 140+, DnB 170-175.
Energy: score < 4 or BPM < 120 → warm_up; 4-6 → building; > 6.5 with BPM ≥ 126 → peak_time; emotional end-of-set tracks → closing; slow/hypnotic → after.
Never invent. When unsure, use `To_Sort`. Also fix `artist`/`title` when the file name was split wrongly.
Edit `plan.json` with a short script for big batches, not by hand.

Alternative if the user prefers another model to do this step (OpenAI, Mistral, Gemini, Ollama...):
```bash
python3 $S classify plan.json --provider mistral --model mistral-small-latest
```

## 4. Preview (Supervisor)
```bash
python3 $S apply plan.json --library "<library folder>" --dry-run
```
Show the user a summary table: track → new name → folder, warnings, number of To_Sort.
**Wait for approval** before step 5.

## 5. Organise (Archivist)
```bash
python3 $S apply plan.json --library "<library folder>" [--write-tags] [--move] [--lang fr]
```
- Copies by default. Use `--move` only if the user explicitly asks.
- `--write-tags` writes BPM + Camelot key into the copies (MP3/FLAC/OGG) for Rekordbox/Serato/Traktor.
- `--lang fr` gives French folder names.
- Re-running is safe: already organised tracks show `SKIP`.

Result:
```
<library>/
├── 01_By_Genre/<Genre>/<Sub_Genre>/124 - 8A - Artist - Title.mp3   ← real files
├── 02_By_Energy/1_Warm_Up.m3u8 … 5_After.m3u8                       ← playlists, no duplicates
├── 03_New_This_Month/YYYY-MM_Month.m3u8
└── .crate_digger_index.json
```

## 6. Report
Tracks organised, split by genre and energy, and the list to check: To_Sort, BPM/key from audio, tag/audio conflicts.
Optionally suggest a harmonic set order. `python3 $S camelot 8A` lists compatible keys (same number A↔B, ±1 on the wheel); order by rising BPM.
