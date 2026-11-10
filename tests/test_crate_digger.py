import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "dj-crate-digger" / "scripts"
SCRIPT = SCRIPTS / "crate_digger.py"
sys.path.insert(0, str(SCRIPTS))
import crate_digger as cd  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("Am", "8A"), ("A minor", "8A"), ("F#m", "11A"), ("Gbm", "11A"), ("Bbm", "3A"),
    ("Ebm", "2A"), ("Bm", "10A"), ("C", "8B"), ("E", "12B"), ("Abmaj", "4B"), ("C major", "8B"),
    ("8a", "8A"), ("08B", "8B"), ("1m", "8A"), ("1d", "8B"), ("6m", "1A"), ("F♯m", "11A"),
    ("", None), ("xyz", None), ("Hm", None), ("Cwhatever", None),
])
def test_to_camelot(raw, expected):
    assert cd.to_camelot(raw) == expected


def test_compatible_keys():
    assert cd.compatible_keys("8A") == ["8A", "9A", "7A", "8B"]
    assert cd.compatible_keys("12B") == ["12B", "1B", "11B", "12A"]
    assert cd.compatible_keys("1A") == ["1A", "2A", "12A", "1B"]


def test_fold_bpm():
    assert cd.fold_bpm(62) == 124
    assert cd.fold_bpm(256) == 128
    assert cd.fold_bpm(174) == 174
    assert cd.fold_bpm(0) is None


def test_guess_from_filename():
    assert cd.guess_from_filename("01 - Artist - Track (Remix)") == {"artist": "Artist", "title": "Track (Remix)"}
    assert cd.guess_from_filename("untitled_groove") == {"title": "untitled groove"}


def test_clean():
    assert cd.clean('AC/DC: "Live"?') == "ACDC Live"
    assert cd.clean("") == "Unknown"


def _plan(tmp_path, **track):
    src = tmp_path / "in"
    src.mkdir(exist_ok=True)
    (src / "a.mp3").write_bytes(b"fake-audio")
    t = {"source": str(src / "a.mp3"), "artist": "Joey", "title": "Flash", "bpm": 126, "key": "8A",
         "genre": "Techno", "sub_genre": "Peak Time", "energy": "peak_time", "duration_s": 300}
    t.update(track)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"tracks": [t]}))
    return plan, src


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, check=True).stdout


def test_apply_end_to_end(tmp_path):
    plan, src = _plan(tmp_path)
    lib = tmp_path / "lib"
    assert "PLAN" in run_cli("apply", plan, "--library", lib, "--dry-run")
    assert not lib.exists()                                    # dry run touches nothing
    assert "OK" in run_cli("apply", plan, "--library", lib)
    assert (lib / "01_By_Genre/Techno/Peak_Time/126 - 8A - Joey - Flash.mp3").exists()
    assert (src / "a.mp3").exists()                            # copy, not move
    assert "Flash" in (lib / "02_By_Energy/3_Peak_Time.m3u8").read_text()
    assert list((lib / "03_New_This_Month").glob("*.m3u8"))
    assert "SKIP" in run_cli("apply", plan, "--library", lib)  # idempotent
    assert len(list((lib / "01_By_Genre").rglob("*.mp3"))) == 1


def test_apply_french_and_to_sort(tmp_path):
    plan, _ = _plan(tmp_path, genre=None, sub_genre=None, energy=None, artist=None)
    lib = tmp_path / "lib"
    run_cli("apply", plan, "--library", lib, "--lang", "fr")
    assert (lib / "01_Par_Genre/A_Trier/126 - 8A - Inconnu - Flash.mp3").exists()


def test_apply_move(tmp_path):
    plan, src = _plan(tmp_path)
    run_cli("apply", plan, "--library", tmp_path / "lib", "--move")
    assert not (src / "a.mp3").exists()


def test_analyze_tags_only(tmp_path):
    from mutagen.id3 import ID3, TBPM, TIT2, TKEY, TPE1
    src = tmp_path / "in"
    src.mkdir()
    f = src / "01 - Wrong - Name.mp3"
    f.write_bytes(b"")
    tags = ID3()
    for frame in (TPE1(encoding=3, text="Real Artist"), TIT2(encoding=3, text="Night Drive"),
                  TBPM(encoding=3, text="62"), TKEY(encoding=3, text="Am")):
        tags.add(frame)
    tags.save(f)
    plan = cd.analyze_folder(src, tmp_path / "plan.json", audio=False)
    t = plan["tracks"][0]
    assert (t["artist"], t["title"], t["bpm"], t["key"], t["key_source"]) == ("Real Artist", "Night Drive", 124, "8A", "tag")


class _FakeLLM(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeLLM.calls.append((self.path, self.headers.get("Authorization"), body))
        tracks = json.loads(body["messages"][1]["content"])["tracks"]
        out = {"tracks": [{"i": t["i"], "genre": "House", "sub_genre": "Deep House", "energy": "warm_up"}
                          for t in tracks]}
        reply = {"choices": [{"message": {"content": "```json\n" + json.dumps(out) + "\n```"}}]}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def test_classify_with_openai_compatible_api(tmp_path, monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _FakeLLM)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    plan, _ = _plan(tmp_path, genre=None, sub_genre=None, energy=None)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    res = cd.classify_plan(plan, model="any-model", base_url=f"http://127.0.0.1:{server.server_port}/v1")
    server.shutdown()
    assert res == {"classified": 1, "requested": 1}
    t = json.loads(plan.read_text())["tracks"][0]
    assert (t["genre"], t["sub_genre"], t["energy"]) == ("House", "Deep House", "warm_up")
    path, auth, body = _FakeLLM.calls[-1]
    assert path == "/v1/chat/completions" and auth == "Bearer test-key" and body["model"] == "any-model"


def test_mcp_tools(tmp_path):
    pytest.importorskip("mcp")
    import crate_digger_mcp as m
    plan, _ = _plan(tmp_path, genre=None, sub_genre=None, energy=None)
    r = json.loads(m.classify_tracks(str(plan), [{"i": 0, "genre": "Techno", "sub_genre": "Driving",
                                                  "energy": "building"}, {"i": 99}]))
    assert r == {"updated": 1, "still_unclassified": 0}
    r = json.loads(m.organize_library(str(plan), str(tmp_path / "lib")))
    assert r["dry_run"] and r["counts"] == {"PLAN": 1}
    assert json.loads(m.camelot_keys(["Am"]))[0]["camelot"] == "8A"


def test_installer(tmp_path):
    import os
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    (tmp_path / ".claude").mkdir()
    subprocess.run([sys.executable, str(ROOT / "install.py")], env=env, check=True, capture_output=True)
    for d in (".agents/skills", ".claude/skills"):
        assert (tmp_path / d / "dj-crate-digger/SKILL.md").exists()
        assert (tmp_path / d / "dj-crate-digger/scripts/crate_digger.py").exists()
    subprocess.run([sys.executable, str(ROOT / "install.py"), "--uninstall"], env=env, check=True,
                   capture_output=True)
    assert not (tmp_path / ".agents/skills/dj-crate-digger").exists()
