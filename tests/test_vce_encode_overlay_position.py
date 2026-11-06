"""章名の焼き込みと、その位置

2 つの欠陥を同時に塞ぐ。

1. **映像ソースでは `--overlay-title` が何もしていなかった。** `drawtext` は
   `combine_audio_with_cover`（音声＋カバー画像の経路）にしか無く、
   `extract_segment`（映像の経路）には入っていなかった。エラーも警告も出ないので、
   「指定したのに字が出ない」としか分からない。
2. 位置が上寄りの中央に固定で、被写体に重なっていた。

位置は `x`/`y` の式なので、文字列を見るだけでは本当に左下へ出るか分からない。
**実際に焼いて画素を見る。** 幾何補正と併用したときに字まで台形に歪まないこと
（`drawtext` が `perspective` より後に来ること）も、同じやり方で確かめる。
"""

import ast
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

VCE_ENCODE = pathlib.Path(__file__).resolve().parents[1] / "bin" / "vce-encode"

W, H = 640, 360


@pytest.fixture(scope="module")
def vce():
    """bin/vce-encode のモジュール直下の定義だけを評価する（既存テストと同じ手口）"""
    tree = ast.parse(VCE_ENCODE.read_text(encoding="utf-8"))
    keep = [
        n for n in tree.body
        if not (isinstance(n, ast.ClassDef) and n.name == "ProjectEncoder")
        and not (isinstance(n, ast.FunctionDef) and n.name == "main")
        and not isinstance(n, ast.If)
    ]
    ns = {"__file__": str(VCE_ENCODE)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(VCE_ENCODE), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        pytest.skip("ffmpeg が無い")
    return exe


# ---------------------------------------------------------------- 式の組み立て


class TestPositions:
    def test_every_position_has_x_and_y(self, vce):
        for name, pair in vce["OVERLAY_POSITIONS"].items():
            assert len(pair) == 2, name

    def test_default_is_bottom_left(self, vce):
        assert vce["DEFAULT_OVERLAY_POSITION"] == "bottom-left"

    def test_center_keeps_the_old_expression(self, vce):
        """従来の見た目へ戻す道を残す（既存の書き出しと揃えたいとき用）"""
        assert vce["OVERLAY_POSITIONS"]["center"] == ("(w-tw)/2", "h*0.325-th/2")

    def test_margins_scale_with_resolution(self, vce):
        """余白は固定画素でなく比率（4K で枠に貼り付かないこと）"""
        for name, (x, y) in vce["OVERLAY_POSITIONS"].items():
            if name == "center":
                continue
            assert "w*" in x or "w-" in x, (name, x)
            assert "h*" in y or "h-" in y, (name, y)


class TestBuildTitleOverlays:
    """時刻の切り出し。セグメントごとに分けて焼くので、ここを外すと字がずれる"""

    def _chapters(self, vce, items):
        return [vce["ChapterInfo"](local_time_ms=ms, title=t, source_index=0)
                for ms, t in items]

    def test_excluded_chapters_get_no_text(self, vce):
        chapters = self._chapters(vce, [(0, "A"), (1000, "--MC"), (2000, "B")])
        out = vce["build_title_overlays"](chapters, "/f.ttf", "bottom-left",
                                          0, 3000, 3000)
        assert len(out) == 2
        assert all("MC" not in f for f in out)

    def test_times_are_relative_to_the_window(self, vce):
        """セグメント先頭を 0 にする（出力時間軸のまま渡すと字が出ない）"""
        chapters = self._chapters(vce, [(10_000, "A"), (12_000, "B")])
        out = vce["build_title_overlays"](chapters, "/f.ttf", "bottom-left",
                                          window_start_ms=10_000,
                                          window_end_ms=14_000,
                                          fallback_end_ms=14_000)
        assert "between(t,0.000,2.000)" in out[0]
        assert "between(t,2.000,4.000)" in out[1]

    def test_chapters_outside_the_window_are_dropped(self, vce):
        chapters = self._chapters(vce, [(0, "A"), (50_000, "B")])
        out = vce["build_title_overlays"](chapters, "/f.ttf", "bottom-left",
                                          window_start_ms=0, window_end_ms=1_000,
                                          fallback_end_ms=60_000)
        assert len(out) == 1 and "A" in out[0]

    def test_a_chapter_runs_until_the_next_valid_one(self, vce):
        """除外章は出力でカットされるので、次の有効章まで続く"""
        chapters = self._chapters(vce, [(0, "A"), (1000, "--cut"), (2000, "B")])
        out = vce["build_title_overlays"](chapters, "/f.ttf", "bottom-left",
                                          0, 5000, 5000)
        assert "between(t,0.000,2.000)" in out[0]

    def test_no_chapters_means_no_filters(self, vce):
        assert vce["build_title_overlays"]([], "/f.ttf", "bottom-left", 0, 1000, 1000) == []

    def test_title_is_escaped(self, vce):
        """コロンやクォートで drawtext の構文が壊れないこと"""
        chapters = self._chapters(vce, [(0, "A:B'C")])
        out = vce["build_title_overlays"](chapters, "/f.ttf", "bottom-left",
                                          0, 1000, 1000)
        assert "\\:" in out[0] and "\\'" in out[0]


# ------------------------------------------------------------------ 実描画


def _mkdir(tmp_path, name):
    """書き出しが混ざらないよう、1 本につき 1 フォルダ"""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _project(tmp_path, ffmpeg, transform=None):
    """2 章の素材と .vce.json を作る（上下左右が判る市松模様）"""
    media = tmp_path / "src.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}:r=15:d=6",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         str(media)], check=True)

    source = {"path": "src.mp4"}
    if transform:
        source["transform"] = transform
    project = tmp_path / "p.vce.json"
    project.write_text(json.dumps({
        "version": "1.0",
        "sources": [source],
        "chapters": [{"local_time_ms": 0, "source_index": 0, "title": "TITLE"}],
    }, ensure_ascii=False), encoding="utf-8")
    return project


def _encode(project, *extra):
    result = subprocess.run(
        [sys.executable, str(VCE_ENCODE), str(project), *extra],
        capture_output=True, text=True, cwd=str(project.parent))
    assert result.returncode == 0, result.stderr[-2000:]
    out = list(project.parent.glob("*_encoded.mp4"))
    assert out, f"出力が無い: {result.stdout[-2000:]}"
    return out[0]


def _ink(ffmpeg, video, tmp_path, name):
    """1 フレームを PGM で取り出し、四分割それぞれの「地（灰）からの外れ量」を返す

    字は白＋黒枠＋半透明の黒箱なので、どこに置かれても灰色からは大きく外れる。
    """
    frame = tmp_path / f"{name}.pgm"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-ss", "1", "-i", str(video),
         "-frames:v", "1", "-pix_fmt", "gray", str(frame)], check=True)

    raw = frame.read_bytes()
    # P5 <w> <h> <maxval>\n<data>
    fields, pos = [], 0
    while len(fields) < 4:
        while raw[pos:pos + 1].isspace():
            pos += 1
        start = pos
        while not raw[pos:pos + 1].isspace():
            pos += 1
        fields.append(raw[start:pos])
    pos += 1
    w, h = int(fields[1]), int(fields[2])
    data = raw[pos:pos + w * h]

    def deviation(x0, x1, y0, y1):
        total = 0
        for y in range(y0, y1):
            row = data[y * w:(y + 1) * w]
            total += sum(abs(row[x] - 128) for x in range(x0, x1))
        return total / max(1, (x1 - x0) * (y1 - y0))

    return {
        "bottom_left":  deviation(0, w // 2, h // 2, h),
        "bottom_right": deviation(w // 2, w, h // 2, h),
        "top_left":     deviation(0, w // 2, 0, h // 2),
        "top_right":    deviation(w // 2, w, 0, h // 2),
    }


class TestBurnedIn:
    """映像ソースで実際に字が乗ること（ここが長く抜けていた）"""

    def test_video_source_gets_the_title(self, tmp_path, ffmpeg):
        """焼き込み無しとの差を見る（無印でも差が出ないなら乗っていない）"""
        without = _mkdir(tmp_path, "without")
        base = _ink(ffmpeg, _encode(_project(without, ffmpeg), "--no-srt"),
                    tmp_path, "plain")

        with_ = _mkdir(tmp_path, "with")
        got = _ink(ffmpeg, _encode(_project(with_, ffmpeg), "--no-srt", "--overlay-title"),
                   tmp_path, "burned")

        assert got["bottom_left"] > base["bottom_left"] + 1.0, (
            f"字が乗っていない: {base} → {got}")

    def test_it_lands_bottom_left(self, tmp_path, ffmpeg):
        project = _project(tmp_path, ffmpeg)
        video = _encode(project, "--no-srt", "--overlay-title")
        ink = _ink(ffmpeg, video, tmp_path, "bl")

        assert ink["bottom_left"] > ink["top_left"], ink
        assert ink["bottom_left"] > ink["top_right"], ink
        assert ink["bottom_left"] > ink["bottom_right"], ink

    def test_position_flag_moves_it(self, tmp_path, ffmpeg):
        project = _project(tmp_path, ffmpeg)
        video = _encode(project, "--no-srt", "--overlay-title",
                        "--overlay-position", "top-right")
        ink = _ink(ffmpeg, video, tmp_path, "tr")
        assert ink["top_right"] > ink["bottom_left"], ink

    def test_text_is_not_warped_by_the_geometry_correction(self, tmp_path, ffmpeg):
        """`drawtext` は `perspective` より後に来ること

        前に置くと字まで台形に歪む。歪むと左右で高さが変わるので、
        左下の濃さが台形補正の有無でほぼ変わらないことを見る。
        """
        flat = _ink(ffmpeg,
                    _encode(_project(_mkdir(tmp_path, "flat"), ffmpeg),
                            "--no-srt", "--overlay-title"),
                    tmp_path, "flat")

        skewed = _ink(ffmpeg,
                      _encode(_project(_mkdir(tmp_path, "skewed"), ffmpeg, transform={
                          "quad": [[20, 10], [W - 30, 4], [14, H - 20], [W - 24, H - 6]],
                          "reference": [W, H],
                      }), "--no-srt", "--overlay-title"),
                      tmp_path, "skewed")

        assert skewed["bottom_left"] == pytest.approx(flat["bottom_left"], rel=0.35), (
            f"台形補正で字の写りが変わった（drawtext が perspective より前）: "
            f"{flat} vs {skewed}")


class TestSkipPath:
    """素通し経路でも字が乗ること

    区間がソース全体を覆うプロジェクトでは再エンコードを省く分岐がある。
    幾何補正で一度踏んだのと同じ穴なので、焼き込みでも塞いでおく。
    """

    def test_full_source_still_gets_the_title(self, tmp_path, ffmpeg):
        project = _project(tmp_path, ffmpeg)
        video = _encode(project, "--no-srt", "--overlay-title")
        ink = _ink(ffmpeg, video, tmp_path, "skip")
        assert ink["bottom_left"] > 1.0, ink
