"""
test_server.py - Web 陶器（server/msw_server）の配管まわり

外部（Cloudflare・Claude・GPU）には触れない。確かめるのは
  - 認証: Access JWT の署名・aud・許可リストを検証し、fail-closed であること
  - アップロード: offset 付き分割送信と再開、他人のジョブが見えないこと
  - 構成: 区間割り（'--' 章はカット）、AI なしの発言録（段落・低確信度）、出典時刻の検証
  - 組版: 文字列が TeX として解釈されず、\\ts{} / \\section{} の界面が保たれること
"""

import json
import pathlib
import sys
import time

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER))

fastapi = pytest.importorskip("fastapi")
jwt = pytest.importorskip("jwt")

from msw_server import analysis, tex
from msw_server.config import Settings
from msw_server.db import JobStore

# --- 認証 ---------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key.public_key()})()


def cfg(**kw):
    base = {"cf_team_domain": "team.cloudflareaccess.com", "cf_aud": "aud-1",
            "allowed_emails": ["ok@example.com"], "dev_email": ""}
    base.update(kw)
    return Settings(**base)


def token(key, **claims):
    now = int(time.time())
    body = {"aud": "aud-1", "iss": "https://team.cloudflareaccess.com",
            "iat": now, "exp": now + 600, "email": "OK@example.com"} | claims
    return jwt.encode(body, key, algorithm="RS256")


def test_access_token_accepted(keypair):
    from msw_server import auth
    assert auth.verify_token(token(keypair), cfg(), FakeJWKS(keypair)) == "ok@example.com"


@pytest.mark.parametrize("claims,status", [
    ({"aud": "other"}, 401),
    ({"iss": "https://evil.cloudflareaccess.com"}, 401),
    ({"exp": int(time.time()) - 10}, 401),
    ({"email": "stranger@example.com"}, 403),
])
def test_access_token_rejected(keypair, claims, status):
    from msw_server import auth
    with pytest.raises(fastapi.HTTPException) as e:
        auth.verify_token(token(keypair, **claims), cfg(), FakeJWKS(keypair))
    assert e.value.status_code == status


def test_empty_allowlist_rejects_everyone(keypair):
    from msw_server import auth
    with pytest.raises(fastapi.HTTPException) as e:
        auth.verify_token(token(keypair), cfg(allowed_emails=[]), FakeJWKS(keypair))
    assert e.value.status_code == 403


def test_dev_email_is_ignored_when_access_is_configured():
    from msw_server import auth
    req = type("R", (), {"headers": {}, "cookies": {}})()
    assert auth.current_email(req, cfg(cf_aud="", dev_email="dev@x")) == "dev@x"
    with pytest.raises(fastapi.HTTPException) as e:
        auth.current_email(req, cfg(dev_email="dev@x"))
    assert e.value.status_code == 401


# --- API（アップロード） ---------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from msw_server import app as app_mod

    settings = cfg(data_dir=tmp_path, max_chunk_bytes=4)
    store = JobStore(settings.db_path)
    who = {"email": "ok@example.com"}
    app_mod.app.dependency_overrides[app_mod.get_cfg] = lambda: settings
    app_mod.app.dependency_overrides[app_mod.get_store] = lambda: store
    app_mod.app.dependency_overrides[app_mod.user] = lambda: who["email"]
    yield TestClient(app_mod.app), store, who
    app_mod.app.dependency_overrides.clear()


def test_chunked_upload_and_resume(client):
    c, store, _ = client
    job = c.post("/api/jobs", json={"filename": "take.wav", "size": 10}).json()
    jid = job["id"]
    assert job["chunk_bytes"] == 4
    assert c.put(f"/api/jobs/{jid}/input?offset=0", content=b"0123").json()["received"] == 4
    # 途中で切れたクライアントは 409 の received から送り直す
    r = c.put(f"/api/jobs/{jid}/input?offset=0", content=b"0123")
    assert r.status_code == 409 and r.json()["detail"]["received"] == 4
    assert c.put(f"/api/jobs/{jid}/input?offset=4", content=b"45678").status_code == 413
    c.put(f"/api/jobs/{jid}/input?offset=4", content=b"4567")
    assert c.post(f"/api/jobs/{jid}/submit").status_code == 409  # まだ 8/10
    c.put(f"/api/jobs/{jid}/input?offset=8", content=b"89")
    assert c.post(f"/api/jobs/{jid}/submit").json()["status"] == "queued"
    assert store.claim(60)["id"] == jid


def test_other_users_jobs_are_invisible(client):
    c, _, who = client
    jid = c.post("/api/jobs", json={"filename": "take.wav", "size": 1}).json()["id"]
    who["email"] = "other@example.com"
    assert c.get(f"/api/jobs/{jid}").status_code == 404
    assert c.get("/api/jobs").json() == []


def test_rejects_non_media_and_unknown_files(client):
    c, _, _ = client
    assert c.post("/api/jobs", json={"filename": "x.php", "size": 1}).status_code == 415
    jid = c.post("/api/jobs", json={"filename": "a.flac", "size": 1}).json()["id"]
    assert c.get(f"/api/jobs/{jid}/files/input.bin").status_code == 404
    assert c.get(f"/api/jobs/{jid}/files/..%2Fjobs.sqlite3").status_code == 404


def test_login_redirect_only_to_allowed_origin(client):
    c, _, _ = client
    settings = cfg(allowed_origins=["https://differance-lab.tokyo"])
    from msw_server import app as app_mod
    app_mod.app.dependency_overrides[app_mod.get_cfg] = lambda: settings
    r = c.get("/login?next=https://evil.example/", follow_redirects=False)
    assert r.headers["location"] == "https://differance-lab.tokyo"
    r = c.get("/login?next=https://differance-lab.tokyo/msw/", follow_redirects=False)
    assert r.headers["location"] == "https://differance-lab.tokyo/msw/"


# --- 構成 ---------------------------------------------------------------

def utt(s, text="はい", dur=2.0, words=None):
    return analysis.Utterance(float(s), float(s) + dur, text,
                              [analysis.Word(w, p) for w, p in (words or [])])


def test_segments_follow_chapters_and_skip_cuts():
    utts = [utt(0), utt(700), utt(1500)]
    chapters = [(0, "--開始前"), (60, "第1楽章"), (1200, "--休憩"), (1400, "第2楽章")]
    segs = analysis.plan_segments(utts, chapters, 20)
    assert [(s.title, s.start_s, s.end_s) for s in segs] == [
        ("第1楽章", 60, 1200), ("第2楽章", 1400, 1502.0)]


def test_segments_fall_back_to_windows():
    segs = analysis.plan_segments([utt(0), utt(2500)], [], 20)
    assert [(s.title, s.start_s, s.end_s) for s in segs] == [
        ("区間 1", 0, 1200), ("区間 2", 1200, 2400), ("区間 3", 2400, 2502.0)]


def test_transcript_groups_paragraphs_by_gap_and_length():
    a = analysis.TranscriptAnalyzer(gap_s=4, max_s=60)
    seg = analysis.Segment("A", 0, 600)
    utts = [utt(10, "ではCから"), utt(13, "もう一度"),   # 間 1 秒 → 同じ段落
            utt(30, "ホルン"),                           # 間 15 秒 → 新しい段落
            *[utt(32 + 3 * i, f"続き{i}") for i in range(25)]]  # 60 秒で切れる
    paras = a.analyze_segment({}, seg, utts)["transcript"]
    assert paras[0]["time"] == "00:00:10"
    assert "".join(r["text"] for r in paras[0]["runs"]) == "ではCから もう一度"
    assert paras[1]["time"] == "00:00:30"
    assert len(paras) == 3 and paras[2]["time"] == "00:01:29"


def test_transcript_marks_low_confidence_words():
    a = analysis.TranscriptAnalyzer(low_conf=0.4)
    u = utt(0, "四小節前から", words=[("四", 0.9), ("小節", 0.2), ("前", 0.3), ("から", 0.95)])
    assert a.runs(u) == [{"text": "四", "low": False}, {"text": "小節前", "low": True},
                         {"text": "から", "low": False}]
    assert a.runs(utt(0, "SRT のみ")) == [{"text": "SRT のみ", "low": False}]


def test_words_json_is_preferred_over_srt(tmp_path):
    srt = tmp_path / "t.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nSRT\n", encoding="utf-8")
    words = tmp_path / "t.words.json"
    words.write_text(json.dumps({"segments": [{"start": 1.0, "end": 2.0, "text": " 語 ",
        "words": [{"word": "語", "start": 1.0, "end": 2.0, "probability": 0.1}]}]}),
        encoding="utf-8")
    [u] = analysis.load_utterances(srt, words)
    assert (u.text, u.words[0].probability) == ("語", 0.1)
    [u] = analysis.load_utterances(srt, tmp_path / "missing.json")
    assert u.text == "SRT"


def test_grounding_marks_invented_timestamps():
    seg = analysis.Segment("第1楽章", 60, 1200)
    utts = [utt(100), utt(400)]
    result = {"topics": [{"title": "A", "start": "00:01:40", "instructions": [
        {"time": "00:06:45", "text": "実在", "parts": []},
        {"time": "00:15:00", "text": "発話が無い", "parts": []},
        {"time": "01:30:00", "text": "区間外", "parts": []},
        {"time": "6:40", "text": "書式違い", "parts": []},
    ]}]}
    out = analysis.ground(result, seg, utts)
    assert out["topics"][0]["verified"] is True
    assert [i["verified"] for i in out["topics"][0]["instructions"]] == [True, False, False, False]


class FakeAnalyzer:
    name = "fake"

    def __init__(self):
        self.seen = []

    def analyze_segment(self, meta, seg, utts):
        self.seen.append((seg.title, [u.text for u in utts]))
        return {"summary": "s", "topics": [], "part_notes": []}


def test_analyze_sends_each_chapter_only_its_own_utterances(tmp_path):
    srt = tmp_path / "t.srt"
    srt.write_text("1\n00:01:00,000 --> 00:01:02,000\n一曲目\n\n"
                   "2\n00:30:00,000 --> 00:30:02,000\n二曲目\n", encoding="utf-8")
    ch = tmp_path / "chapters.txt"
    ch.write_text("# source: x.mp4\n0:00:00.000 A\n0:20:00.000 B\n", encoding="utf-8")
    fa = FakeAnalyzer()
    report = analysis.analyze(srt, ch, {}, fa, 20)
    assert fa.seen == [("A", ["一曲目"]), ("B", ["二曲目"])]
    assert report["chaptered"] and [s["title"] for s in report["segments"]] == ["A", "B"]
    assert report["analyzer"] == "fake"


def test_default_analyzer_uses_no_external_service():
    assert isinstance(analysis.make_analyzer("transcript"), analysis.TranscriptAnalyzer)
    with pytest.raises(ValueError):
        analysis.make_analyzer("claude")
    assert Settings().analyzer == "transcript"


# --- 組版 ---------------------------------------------------------------

def test_tex_escapes_hostile_text_and_keeps_interfaces():
    report = {
        "meta": {"title": r"\input{/etc/passwd} 100%", "pieces": ["A&B"]},
        "segments": [{
            "title": "第1楽章 #1", "start": "00:01:00", "end": "00:20:00", "summary": "$x$",
            "part_notes": [], "topics": [{
                "title": "C～D", "start": "00:01:40", "verified": True,
                "instructions": [{"time": "00:02:00", "text": r"\write18{rm -rf ~}",
                                  "parts": ["Hr"], "verified": False}]}]}]}
    out = tex.render(report)
    assert r"\input{/etc" not in out and r"\write18{" not in out
    assert r"\textbackslash{}input\{/etc/passwd\} 100\%" in out
    assert r"A\&B" in out and r"\$x\$" in out
    assert r"\section{第1楽章 \#1 \ts{00:01:00}〜\ts{00:20:00}}" in out
    assert r"\item \ts{00:02:00}\unverified " in out
    # tex-link-timestamps が差し替える定義行（1行）
    assert "\\newcommand{\\ts}[1]{\\texttt{\\small [#1]}}\n" in out


def test_tex_renders_transcript_with_low_confidence_marks():
    report = {"analyzer": "transcript", "meta": {}, "segments": [{
        "title": "A", "start": "00:00:00", "end": "00:10:00", "summary": "", "topics": [],
        "part_notes": [], "transcript": [{"time": "00:00:10", "runs": [
            {"text": "練習番号", "low": False}, {"text": "#C_", "low": True}]}]}]}
    out = tex.render(report)
    assert r"\noindent\ts{00:00:10} 練習番号\lowconf{\#C\_}\par" in out
    assert "要約していません" in out


def test_tex_does_not_wrap_malformed_time():
    assert tex.ts("12:34") == "12:34"
    assert tex.ts("01:02:03") == r"\ts{01:02:03}"


def test_report_schema_is_strict():
    def walk(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for v in node["properties"].values():
                walk(v)
        if node.get("type") == "array":
            walk(node["items"])
    walk(analysis.REPORT_SCHEMA)
    json.dumps(analysis.REPORT_SCHEMA)
