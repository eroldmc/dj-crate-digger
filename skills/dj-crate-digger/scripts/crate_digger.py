#!/usr/bin/env python3
"""DJ Crate Digger - analyse, normalise and organise a DJ music library.

  analyze  <source_dir> --out plan.json        tags + BPM + Camelot key + energy score
                                               (reuses Serato / Rekordbox analysis and playlists)
  classify plan.json --provider P --model M    fill genre/sub_genre/energy with any LLM API
           (or let your AI agent fill them in plan.json itself)
  apply    plan.json --library <dir> [--dry-run] [--move] [--write-tags] [--lang en|fr]
  camelot  <key>...                            convert keys to Camelot (Am -> 8A)
"""
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

__version__ = "1.2.0"

AUDIO_EXT = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENHARMONIC = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#",
              "CB": "B", "FB": "E", "E#": "F", "B#": "C"}
# Camelot wheel: minor = A, major = B
CAMELOT_MINOR = {"G#": 1, "D#": 2, "A#": 3, "F": 4, "C": 5, "G": 6, "D": 7, "A": 8,
                 "E": 9, "B": 10, "F#": 11, "C#": 12}
CAMELOT_MAJOR = {"B": 1, "F#": 2, "C#": 3, "G#": 4, "D#": 5, "A#": 6, "F": 7, "C": 8,
                 "G": 9, "D": 10, "A": 11, "E": 12}
ENERGY_LEVELS = ["warm_up", "building", "peak_time", "closing", "after"]

GENRES = {
    "House": ["Deep House", "Tech House", "Progressive House", "Organic House", "Afro House",
              "Melodic House", "Minimal House", "Jackin House", "Soulful House", "Electro House"],
    "Techno": ["Melodic Techno", "Peak Time", "Driving", "Hard Techno", "Minimal", "Dub Techno",
               "Industrial", "Hypnotic", "Acid", "Detroit"],
    "Trance": ["Progressive Trance", "Uplifting", "Psytrance", "Tech Trance"],
    "Drum_and_Bass": ["Liquid", "Neurofunk", "Jump Up", "Jungle"],
    "Bass": ["Dubstep", "UK Garage", "Breaks", "Bass House"],
    "Disco": ["Nu Disco", "Indie Dance", "Italo", "Classic Disco"],
    "Downtempo": ["Ambient", "Chill", "Organic Downtempo", "Trip Hop"],
    "Hip-Hop": ["Hip-Hop", "R&B", "Trap", "Afrobeats", "Amapiano"],
    "Pop": ["Dance Pop", "Electro Pop", "Edits"],
}

LABELS = {
    "en": {"genre": "01_By_Genre", "energy": "02_By_Energy", "new": "03_New_This_Month",
           "to_sort": "To_Sort", "unknown": "Unknown",
           "levels": ["1_Warm_Up", "2_Building", "3_Peak_Time", "4_Closing", "5_After"],
           "months": ["January", "February", "March", "April", "May", "June", "July",
                      "August", "September", "October", "November", "December"]},
    "fr": {"genre": "01_Par_Genre", "energy": "02_Par_Energie", "new": "03_Nouveautes_Du_Mois",
           "to_sort": "A_Trier", "unknown": "Inconnu",
           "levels": ["1_Warm_Up", "2_Building", "3_Peak_Time", "4_Closing", "5_After"],
           "months": ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet",
                      "Aout", "Septembre", "Octobre", "Novembre", "Decembre"]},
}


def log(msg):
    print(msg, file=sys.stderr)


# ---------- Harmonic Control ----------
def to_camelot(raw):
    """'Am', 'A minor', 'F#m', 'Gbmaj', 'Bbm', '8A', '1m' (Open Key)... -> Camelot ('8A')."""
    if not raw:
        return None
    s = str(raw).strip().replace("♯", "#").replace("♭", "b")
    m = re.fullmatch(r"0?(\d{1,2})\s*([ABab])", s)                     # already Camelot
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1))}{m.group(2).upper()}"
    m = re.fullmatch(r"0?(\d{1,2})\s*([mdMD])", s)                     # Open Key: 1m = 8A
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{(int(m.group(1)) + 6) % 12 + 1}{'A' if m.group(2).lower() == 'm' else 'B'}"
    m = re.fullmatch(r"([A-Ga-g])\s*([#b]?)\s*(.*)", s)
    if not m:
        return None
    note = m.group(1).upper() + {"#": "#", "b": "B"}.get(m.group(2), "")
    note = ENHARMONIC.get(note, note)
    if note not in NOTES:
        return None
    mode = m.group(3).strip().lower()
    if mode not in ("", "m", "-", "maj", "major", "dur", "moll") and not mode.startswith(("min", "maj")):
        return None
    minor = mode in ("m", "-", "moll") or mode.startswith("min")
    return f"{CAMELOT_MINOR[note]}A" if minor else f"{CAMELOT_MAJOR[note]}B"


def compatible_keys(camelot):
    """Harmonically compatible Camelot keys: same, +/-1, relative major/minor."""
    m = re.fullmatch(r"(\d{1,2})([AB])", camelot or "")
    if not m:
        return []
    n, l = int(m.group(1)), m.group(2)
    return [f"{n}{l}", f"{n % 12 + 1}{l}", f"{(n - 2) % 12 + 1}{l}", f"{n}{'B' if l == 'A' else 'A'}"]


# ---------- Digger ----------
def read_tags(path):
    from mutagen import File
    try:
        audio = File(path)
    except Exception:
        audio = None
    t = audio.tags if audio is not None else None
    if t is None:                       # damaged audio stream: tags may still be readable
        try:
            from mutagen.id3 import ID3
            t = ID3(path)
        except Exception:
            return {}

    def first(*keys):
        for k in keys:
            try:
                v = t.get(k)
            except Exception:
                v = None
            if v is None:
                continue
            v = v.text if hasattr(v, "text") else v
            if isinstance(v, (list, tuple)):
                v = v[0] if v else None
            if v not in (None, ""):
                return str(v)
        return None

    out = {
        "title": first("TIT2", "title", "\xa9nam", "TITLE"),
        "artist": first("TPE1", "artist", "\xa9ART", "ARTIST"),
        "album": first("TALB", "album", "\xa9alb", "ALBUM"),
        "label": first("TPUB", "organization", "LABEL", "label"),
        "year": first("TDRC", "date", "\xa9day", "DATE", "year"),
        "genre_tag": first("TCON", "genre", "\xa9gen", "GENRE"),
        "bpm_tag": first("TBPM", "bpm", "BPM", "tmpo"),
        "key_tag": first("TKEY", "initialkey", "INITIALKEY", "key", "KEY",
                         "----:com.apple.iTunes:initialkey"),
    }
    return {k: v for k, v in out.items() if v}


def guess_from_filename(stem):
    stem = re.sub(r"^\d{1,3}[\s._-]+", "", stem)                        # track number
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s+–\s+", stem) if p.strip()]
    if len(parts) >= 2:
        return {"artist": parts[0], "title": " - ".join(parts[1:])}
    return {"title": stem.replace("_", " ").strip()}


def fold_bpm(bpm):
    bpm = float(bpm)
    if bpm <= 0:
        return None
    while bpm < 85:
        bpm *= 2
    while bpm > 175:
        bpm /= 2
    return round(bpm)


KS_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KS_MIN = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def analyse_audio(path):
    import numpy as np
    import librosa
    dur = librosa.get_duration(path=str(path))
    offset = max(0.0, dur / 2 - 45) if dur > 120 else 0.0
    y, sr = librosa.load(str(path), sr=22050, mono=True, offset=offset, duration=90)
    if y.size < sr * 5:
        return {"duration_s": round(dur)}
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = fold_bpm(float(np.atleast_1d(tempo)[0]))
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y), sr=sr).mean(axis=1)
    best, conf = None, -2.0
    for i in range(12):
        for prof, minor in ((KS_MAJ, False), (KS_MIN, True)):
            r = float(np.corrcoef(chroma, np.roll(prof, i))[0, 1])
            if r > conf:
                best, conf = (NOTES[i], minor), r
    rms = float(librosa.feature.rms(y=y).mean())
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    onset = float(librosa.onset.onset_strength(y=y, sr=sr).mean())
    score = (min(rms / 0.25, 1) * 3.5 + min(centroid / 4000, 1) * 2.5          # loudness, brightness
             + min(onset / 2.5, 1) * 2.5 + min(max((bpm or 0) - 100, 0) / 40, 1) * 1.5)  # density, tempo
    return {"duration_s": round(dur), "bpm_detected": bpm,
            "key_detected": f"{best[0]}{'m' if best[1] else ''}", "key_confidence": round(conf, 2),
            "energy_score": round(max(1, min(10, score)), 1)}


# ---------- DJ software libraries: Serato + Rekordbox ----------
def _norm_path(p):
    return unicodedata.normalize("NFC", str(p).replace("\\", "/")).lstrip("/").lower()


class DJLibrary:
    """Tracks known by a DJ app, keyed by normalised path. Serato stores paths relative to the
    drive root and Rekordbox absolute ones: both are matched on the end of the real path."""

    def __init__(self, name, tracks=None):
        self.name = name
        self.tracks = tracks or {}
        self.by_name = {}
        for rel in self.tracks:
            self.by_name.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)

    def __len__(self):
        return len(self.tracks)

    def lookup(self, path):
        full = _norm_path(Path(path).resolve())
        for rel in self.by_name.get(full.rsplit("/", 1)[-1], []):
            if full == rel or full.endswith("/" + rel):
                return self.tracks[rel]
        return None


# Serato: _Serato_/database V2 + Subcrates/*.crate (rewritten by Serato 3, 4 and 5 on quit)
SERATO_FIELDS = {"pfil": "path", "tsng": "title", "tart": "artist", "talb": "album", "tgen": "genre_tag",
                 "tbpm": "bpm", "tkey": "key", "tlbl": "label", "ttyr": "year", "tcom": "comment"}


def _serato_tlv(buf):
    """Serato binary format: 4-byte ASCII tag, 4-byte big-endian length, payload."""
    i = 0
    while i + 8 <= len(buf):
        tag = buf[i:i + 4].decode("latin-1")
        size = int.from_bytes(buf[i + 4:i + 8], "big")
        yield tag, buf[i + 8:i + 8 + size]
        i += 8 + size


def _serato_text(data):
    return data.decode("utf-16-be", errors="replace").rstrip("\x00").strip()


def find_serato_dirs(source):
    """_Serato_ folders that can describe files under `source`: the home one (~/Music/_Serato_)
    and the one at the root of the drive holding the music (external drives / USB sticks)."""
    src = Path(source).expanduser().resolve()
    candidates = [Path.home() / "Music" / "_Serato_"]
    parts = src.parts
    if len(parts) > 2 and parts[1].lower() in ("volumes", "media", "mnt"):           # macOS / Linux drives
        candidates.append(Path(*parts[:3]) / "_Serato_")
        if parts[1].lower() == "media" and len(parts) > 3:
            candidates.append(Path(*parts[:4]) / "_Serato_")
    candidates.append(Path(src.anchor) / "_Serato_")                                  # Windows drive root
    out = []
    for c in candidates:
        if (c / "database V2").is_file() and c not in out:
            out.append(c)
    return out


def read_serato_library(serato_dir):
    """Parse '_Serato_/database V2' and Subcrates/*.crate -> {path: {title, ..., bpm, key, playlists}}."""
    serato_dir = Path(serato_dir)
    tracks = {}
    for tag, data in _serato_tlv((serato_dir / "database V2").read_bytes()):
        if tag != "otrk":
            continue
        t = {}
        for ftag, fdata in _serato_tlv(data):
            if ftag in SERATO_FIELDS and fdata:
                value = _serato_text(fdata)
                if value:
                    t[SERATO_FIELDS[ftag]] = value
        if t.get("path"):
            tracks[_norm_path(t.pop("path"))] = t
    crates_dir = serato_dir / "Subcrates"
    if crates_dir.is_dir():
        for crate in sorted(crates_dir.glob("*.crate")):
            name = crate.stem.replace("%%", " / ")
            for tag, data in _serato_tlv(crate.read_bytes()):
                if tag != "otrk":
                    continue
                for ftag, fdata in _serato_tlv(data):
                    if ftag == "ptrk":
                        key = _norm_path(_serato_text(fdata))
                        tracks.setdefault(key, {}).setdefault("playlists", []).append(name)
    return tracks


# Rekordbox: collection XML (File > Export Collection in xml format)
REKORDBOX_FIELDS = {"Name": "title", "Artist": "artist", "Album": "album", "Genre": "genre_tag",
                    "AverageBpm": "bpm", "Tonality": "key", "Label": "label", "Year": "year",
                    "Comments": "comment"}


def _rekordbox_location(uri):
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(uri).path) if uri.startswith("file:") else uri
    return _norm_path(path)                                      # /C:/Users/... -> c:/users/...


def is_rekordbox_xml(path):
    try:
        with open(path, "rb") as f:
            return b"<DJ_PLAYLISTS" in f.read(4096)
    except OSError:
        return False


def find_rekordbox_xml(source):
    """Most recent Rekordbox collection export in the usual places."""
    home = Path.home()
    folders = [Path(source).expanduser(), home / "Music", home / "Music" / "rekordbox", home / "Documents",
               home / "Documents" / "rekordbox", home / "Desktop", home / "Downloads"]
    found = []
    for d in folders:
        if d.is_dir():
            found += [f for f in d.glob("*.xml") if f.is_file() and is_rekordbox_xml(f)]
    return sorted(set(found), key=lambda f: f.stat().st_mtime, reverse=True)[:1]


def read_rekordbox_xml(xml_path):
    """Parse a Rekordbox collection XML -> {path: {title, ..., bpm, key, playlists}}."""
    import xml.etree.ElementTree as ET
    root = ET.parse(xml_path).getroot()
    tracks, by_id = {}, {}
    collection = root.find("COLLECTION")
    for el in (collection if collection is not None else []):
        if el.tag != "TRACK" or not el.get("Location"):
            continue
        t = {}
        for attr, field in REKORDBOX_FIELDS.items():
            value = (el.get(attr) or "").strip()
            if value and not (field in ("bpm", "year") and value in ("0", "0.00")):
                t[field] = value
        key = _rekordbox_location(el.get("Location"))
        tracks[key] = t
        if el.get("TrackID"):
            by_id[el.get("TrackID")] = key

    def walk(node, trail):
        for child in node.findall("NODE"):
            name = child.get("Name", "")
            if child.get("Type") == "1":                           # playlist
                label = " / ".join(trail + [name])
                for tr in child.findall("TRACK"):
                    ref = tr.get("Key", "")
                    key = by_id.get(ref) if child.get("KeyType", "0") == "0" else _rekordbox_location(ref)
                    if key in tracks:
                        tracks[key].setdefault("playlists", []).append(label)
            else:                                                  # folder
                walk(child, trail + [name])

    playlists = root.find("PLAYLISTS")
    if playlists is not None:
        for top in playlists.findall("NODE"):                      # ROOT
            walk(top, [])
    return tracks


def load_libraries(source, serato="auto", rekordbox="auto"):
    """DJ app libraries describing the tracks, in priority order (Serato first, then Rekordbox)."""
    libs = []
    jobs = []
    if serato not in (None, False, "off", "none"):
        dirs = find_serato_dirs(source) if serato == "auto" else [Path(serato).expanduser()]
        jobs += [("serato", d, read_serato_library) for d in dirs]
    if rekordbox not in (None, False, "off", "none"):
        files = find_rekordbox_xml(source) if rekordbox == "auto" else [Path(rekordbox).expanduser()]
        jobs += [("rekordbox", f, read_rekordbox_xml) for f in files]
    for name, path, reader in jobs:
        try:
            lib = DJLibrary(name, reader(path))
            log(f"{name.capitalize()}: {len(lib)} tracks read from {path}")
            libs.append(lib)
        except Exception as e:
            log(f"! {name} library not readable ({path}): {e}")
    return libs


def analyze_folder(source, out="plan.json", audio=True, serato="auto", rekordbox="auto",
                   force_audio=False):
    src = Path(source).expanduser()
    if not src.is_dir():
        raise FileNotFoundError(f"Not a folder: {src}")
    files = sorted(p for p in src.rglob("*") if p.suffix.lower() in AUDIO_EXT and p.is_file())
    if audio:
        import importlib.util
        if importlib.util.find_spec("librosa") is None:
            log("! librosa not installed: tags only (pip install librosa soundfile)")
            audio = False
    libs = load_libraries(src, serato, rekordbox)
    tracks = []
    for i, p in enumerate(files, 1):
        log(f"[{i}/{len(files)}] {p.name}")
        info = {"source": str(p.resolve()), **guess_from_filename(p.stem), **read_tags(p)}
        lib_bpm = lib_key = None
        for lib in reversed(libs):                    # higher-priority libraries win
            hit = lib.lookup(p)
            if not hit:
                continue
            for k in ("title", "artist", "album", "label", "year", "genre_tag", "comment"):
                if hit.get(k):
                    info[k] = hit[k]                  # what the DJ sees (and edited) in the app
            if hit.get("playlists"):
                info[f"{lib.name}_playlists"] = hit["playlists"]
            try:
                b = fold_bpm(hit["bpm"].replace(",", ".")) if hit.get("bpm") else None
            except ValueError:
                b = None
            if b:
                lib_bpm = (b, lib.name)
            if to_camelot(hit.get("key")):
                lib_key = (to_camelot(hit["key"]), lib.name)
        if audio and (force_audio or not (lib_bpm and lib_key)):   # already analysed: skip
            try:
                info.update(analyse_audio(p))
            except Exception as e:
                info["audio_error"] = str(e)[:200]
        warnings = []
        bpm = None
        if info.get("bpm_tag"):
            try:
                bpm = fold_bpm(str(info["bpm_tag"]).replace(",", "."))
            except ValueError:
                pass
        info["bpm"] = (lib_bpm and lib_bpm[0]) or bpm or info.get("bpm_detected")
        info["bpm_source"] = (lib_bpm[1] if lib_bpm else "tag" if bpm
                              else "audio" if info.get("bpm_detected") else None)
        cam = to_camelot(info.get("key_tag"))
        info["key"] = (lib_key and lib_key[0]) or cam or to_camelot(info.get("key_detected"))
        info["key_source"] = (lib_key[1] if lib_key else "tag" if cam
                              else "audio" if info.get("key_detected") else None)
        if lib_key and cam and lib_key[0] != cam:
            warnings.append(f"key {lib_key[1]} {lib_key[0]} vs tag {cam}")
        if info.get("bpm_detected") and bpm and abs(info["bpm_detected"] - bpm) > 2:
            warnings.append(f"BPM tag {bpm} vs audio {info['bpm_detected']}")
        if info.get("key_detected") and cam and to_camelot(info["key_detected"]) != cam:
            warnings.append(f"key tag {cam} vs audio {to_camelot(info['key_detected'])}")
        if not info.get("artist"):
            warnings.append("unknown artist")
        if warnings:
            info["warnings"] = warnings
        info.update({"genre": None, "sub_genre": None, "energy": None})   # filled by the AI step
        tracks.append(info)
    plan = {"version": __version__, "tracks": tracks}
    if out:
        Path(out).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"{len(tracks)} tracks analysed -> {out}")
    return plan


# ---------- Musicologist (any LLM via OpenAI-compatible API) ----------
PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "lmstudio": ("http://localhost:1234/v1", None),
}

CLASSIFY_PROMPT = """You are an expert DJ and music librarian. For each track, choose:
- "genre": one of {genres}
- "sub_genre": a precise sub-genre (examples: {examples})
- "energy": one of {levels}
Clues, most reliable first: serato_playlists / rekordbox_playlists (the DJ's own crates and playlists),
genre_tag, artist/label/title you know, bpm, energy_score (1-10), key.
Reference BPM: House 118-126, Tech House 124-128, Melodic Techno 120-126, Peak Time Techno 128-135,
Hard Techno 140+, DnB 170-175. Energy: score<4 or bpm<120 -> warm_up; 4-6 -> building;
>6.5 and bpm>=126 -> peak_time; emotional/melodic end-of-set -> closing; slow/hypnotic -> after.
If unsure use genre "To_Sort". Never invent artists. Reply with JSON only:
{{"tracks":[{{"i":0,"genre":"...","sub_genre":"...","energy":"..."}}]}}"""


def _chat(base_url, api_key, model, messages, json_mode=True, timeout=120):
    body = {"model": model, "messages": messages, "temperature": 0}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


def classify_plan(plan_path, provider=None, model=None, base_url=None, api_key=None,
                  batch=25, force=False):
    if not model:
        raise ValueError("--model is required (any chat model of your provider)")
    default_url, key_env = PROVIDERS.get(provider or "", (None, None))
    base_url = base_url or os.environ.get("LLM_BASE_URL") or default_url
    if not base_url:
        raise ValueError(f"unknown provider; use one of {', '.join(PROVIDERS)} or --base-url")
    api_key = api_key or (os.environ.get(key_env) if key_env else None) or os.environ.get("LLM_API_KEY")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    todo = [i for i, t in enumerate(plan["tracks"]) if force or not t.get("genre")]
    keep = ("artist", "title", "album", "label", "year", "genre_tag", "serato_playlists", "rekordbox_playlists",
            "comment", "bpm", "key", "energy_score")
    system = CLASSIFY_PROMPT.format(
        genres=", ".join(list(GENRES) + ["To_Sort"]),
        examples=", ".join(s for subs in GENRES.values() for s in subs[:3]),
        levels=", ".join(ENERGY_LEVELS))
    done = 0
    for start in range(0, len(todo), batch):
        idx = todo[start:start + batch]
        items = [{"i": i, **{k: plan["tracks"][i].get(k) for k in keep if plan["tracks"][i].get(k)}}
                 for i in idx]
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": json.dumps({"tracks": items}, ensure_ascii=False)}]
        try:
            content = _chat(base_url, api_key, model, messages, json_mode=True)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise
            content = _chat(base_url, api_key, model, messages, json_mode=False)  # no JSON mode
        for r in _parse_json(content).get("tracks", []):
            i = r.get("i")
            if i not in idx:
                continue
            t = plan["tracks"][i]
            t["genre"] = r.get("genre") or "To_Sort"
            t["sub_genre"] = r.get("sub_genre") or None
            t["energy"] = r.get("energy") if r.get("energy") in ENERGY_LEVELS else None
            t["classified_by"] = model
            done += 1
        log(f"classified {min(start + batch, len(todo))}/{len(todo)}")
    Path(plan_path).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"classified": done, "requested": len(todo)}


# ---------- Archivist ----------
def clean(s, maxlen=80, fallback="Unknown"):
    s = unicodedata.normalize("NFC", str(s or "")).strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:maxlen] or fallback


def folder_name(s):
    return clean(s, 60).replace(" ", "_")


def write_tags(path, bpm, key):
    try:
        from mutagen import File
        from mutagen.id3 import TBPM, TKEY
        a = File(path)
        if a is None:
            return
        ext = path.suffix.lower()
        if ext == ".mp3":
            if a.tags is None:
                a.add_tags()
            if bpm:
                a.tags.add(TBPM(encoding=3, text=str(bpm)))
            if key:
                a.tags.add(TKEY(encoding=3, text=key))
        elif ext in (".flac", ".ogg"):
            if bpm:
                a["BPM"] = str(bpm)
            if key:
                a["INITIALKEY"] = key
        else:
            return
        a.save()
    except Exception as e:
        log(f"  ! tags not written ({path.name}): {e}")


def apply_plan(plan_path, library, dry_run=False, move=False, tags=False, lang="en"):
    L = LABELS.get(lang, LABELS["en"])
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    lib = Path(library).expanduser()
    today = date.today()
    month = f"{today:%Y-%m}_{L['months'][today.month - 1]}"
    levels = dict(zip(ENERGY_LEVELS, L["levels"]))
    playlists, report = {}, []
    idx_path = lib / ".crate_digger_index.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else {}
    for t in plan["tracks"]:
        src = Path(t["source"])
        if not src.exists():
            report.append({"status": "ERROR", "source": src.name, "dest": "file not found"})
            continue
        artist = clean(t.get("artist"), fallback=L["unknown"])
        name = (f"{t.get('bpm') or '000'} - {t.get('key') or 'XX'} - {artist} - "
                f"{clean(t.get('title') or src.stem)}{src.suffix.lower()}")
        genre = t.get("genre") or L["to_sort"]
        dest_dir = lib / L["genre"] / folder_name(L["to_sort"] if genre == "To_Sort" else genre)
        if t.get("sub_genre"):
            dest_dir /= folder_name(t["sub_genre"])
        sig = f"{src.name}|{src.stat().st_size}"
        if sig in index and (lib / index[sig]).exists():
            report.append({"status": "SKIP", "source": src.name, "dest": index[sig]})
            continue
        dest, n = dest_dir / name, 2
        while dest.exists() and dest.resolve() != src.resolve():
            dest = dest_dir / f"{Path(name).stem} ({n}){src.suffix.lower()}"
            n += 1
        rel = dest.relative_to(lib).as_posix()
        if dry_run:
            report.append({"status": "PLAN", "source": src.name, "dest": rel})
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (shutil.move if move else shutil.copy2)(str(src), str(dest))
            if tags:
                write_tags(dest, t.get("bpm"), t.get("key"))
            index[sig] = rel
            report.append({"status": "OK", "source": src.name, "dest": rel})
        lists = [f"{L['new']}/{month}.m3u8"]
        if t.get("energy") in levels:
            lists.append(f"{L['energy']}/{levels[t['energy']]}.m3u8")
        for pl in lists:
            playlists.setdefault(pl, []).append((t, dest))
    if not dry_run:
        lib.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
        for pl, items in playlists.items():
            p = lib / pl
            p.parent.mkdir(parents=True, exist_ok=True)
            lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else ["#EXTM3U"]
            have = set(lines)
            for t, dest in sorted(items, key=lambda x: x[0].get("bpm") or 0):
                rel = "../" + dest.relative_to(lib).as_posix()
                if rel not in have:
                    lines += [f"#EXTINF:{t.get('duration_s', -1)},"
                              f"{t.get('artist') or L['unknown']} - {t.get('title') or dest.stem}", rel]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


# ---------- CLI ----------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="crate-digger", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="read tags, detect BPM/key/energy")
    a.add_argument("source")
    a.add_argument("--out", default="plan.json")
    a.add_argument("--no-audio", action="store_true", help="tags only, no audio analysis")
    a.add_argument("--serato", default="auto",
                   help="reuse Serato analysis: auto (default), off, or the path of a _Serato_ folder")
    a.add_argument("--rekordbox", default="auto",
                   help="reuse Rekordbox analysis: auto (default, finds your latest collection XML export), "
                        "off, or the path of the XML")
    a.add_argument("--force-audio", action="store_true",
                   help="analyse audio even for tracks Serato/Rekordbox already analysed")
    c = sub.add_parser("classify", help="fill genre/sub_genre/energy with an LLM API")
    c.add_argument("plan")
    c.add_argument("--provider", choices=list(PROVIDERS))
    c.add_argument("--model", required=True)
    c.add_argument("--base-url", help="any OpenAI-compatible endpoint")
    c.add_argument("--api-key", help="defaults to the provider env var or LLM_API_KEY")
    c.add_argument("--batch", type=int, default=25)
    c.add_argument("--force", action="store_true", help="re-classify tracks that already have a genre")
    b = sub.add_parser("apply", help="rename, organise, build playlists")
    b.add_argument("plan")
    b.add_argument("--library", required=True)
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--move", action="store_true", help="move instead of copy")
    b.add_argument("--write-tags", action="store_true", help="write BPM + Camelot key into the copies")
    b.add_argument("--lang", choices=list(LABELS), default="en", help="folder name language")
    k = sub.add_parser("camelot", help="convert keys to Camelot")
    k.add_argument("keys", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        analyze_folder(args.source, args.out, audio=not args.no_audio, serato=args.serato,
                       rekordbox=args.rekordbox, force_audio=args.force_audio)
    elif args.cmd == "classify":
        print(json.dumps(classify_plan(args.plan, args.provider, args.model, args.base_url,
                                       args.api_key, args.batch, args.force)))
    elif args.cmd == "apply":
        for r in apply_plan(args.plan, args.library, args.dry_run, args.move, args.write_tags, args.lang):
            print(f"{r['status']:5}  {r['source']}  ->  {r['dest']}")
    else:
        for key in args.keys:
            cam = to_camelot(key)
            print(f"{key}\t{cam or '?'}\t{' '.join(compatible_keys(cam))}")


if __name__ == "__main__":
    main()
