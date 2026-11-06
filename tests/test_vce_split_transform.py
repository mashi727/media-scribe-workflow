"""vce-split の幾何補正と焼き込み位置

`vce-encode`（1 本にまとめる）だけが補正に対応し、`vce-split`（曲ごとに分ける）
が対応していない状態は、**同じプロジェクトから作った 2 つの成果物で絵が違う**
ことを意味する。しかも vce-split は補正を無視するのではなく、

    TypeError: unsupported operand type(s) for /: 'PosixPath' and 'dict'

で**開くことすらできなかった**（chaptr が補正付きソースを
`{"path": ..., "transform": {...}}` と書くため）。

幾何の実装は `bin/_vce_geometry.py` で共有しているので、ここで確かめるのは
「vce-split がそれを**使っているか**」。使い忘れは静かなので、実際に焼いて
画素で見る。
"""

import ast
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VCE_SPLIT = ROOT / "bin" / "vce-split"
VCE_ENCODE = ROOT / "bin" / "vce-encode"
GEOMETRY = ROOT / "bin" / "_vce_geometry.py"

W, H = 640, 360


@pytest.fixture(scope="module")
def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        pytest.skip("ffmpeg が無い")
    return exe


def _ns(script):
    tree = ast.parse(script.read_text(encoding="utf-8"))
    keep = [
        n for n in tree.body
        if not (isinstance(n, ast.ClassDef) and n.name in ("ProjectEncoder", "ProjectSplitter"))
        and not (isinstance(n, ast.FunctionDef) and n.name == "main")
        and not isinstance(n, ast.If)
    ]
    ns = {"__file__": str(script)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(script), "exec"), ns)
    return ns


class TestSharedGeometry:
    """幾何の出どころが 1 つであること

    複製すると、片方だけ直したときに「まとめた版と曲ごとの版で絵が違う」
    という、気づくのに最も時間のかかる壊れ方をする。
    """

    def test_the_shared_module_exists(self):
        assert GEOMETRY.exists()

    @pytest.mark.parametrize("name", ["Transform", "quad_for_rotation",
                                      "rect_for_rotation", "OVERLAY_POSITIONS",
                                      "build_title_overlays", "escape_drawtext"])
    def test_definitions_live_only_in_the_shared_module(self, name):
        """bin のスクリプト本体に定義が残っていないこと"""
        for script in (VCE_ENCODE, VCE_SPLIT):
            src = script.read_text(encoding="utf-8")
            assert f"\ndef {name}(" not in src, f"{script.name} に {name} の定義が残っている"
            assert f"\nclass {name}" not in src, f"{script.name} に {name} の定義が残っている"
            assert f"\n{name} = " not in src, f"{script.name} に {name} の定義が残っている"

    def test_both_scripts_get_the_same_objects(self):
        enc, spl = _ns(VCE_ENCODE), _ns(VCE_SPLIT)
        assert enc["Transform"] is spl["Transform"]
        assert enc["OVERLAY_POSITIONS"] is spl["OVERLAY_POSITIONS"]


class TestLoadSources:
    def test_dict_sources_are_accepted(self):
        """以前は TypeError で開けなかった形"""
        ns = _ns(VCE_SPLIT)
        t = ns["Transform"].from_dict({"rotate_deg": 2.0})
        assert t is not None and t.rotate_deg == pytest.approx(2.0)

    def test_source_file_carries_a_transform(self):
        ns = _ns(VCE_SPLIT)
        src = ns["SourceFile"](path=pathlib.Path("x.mp4"))
        assert src.transform is None       # 既定は補正なし


class TestDisplaySize:
    """補正は表示寸法（SAR を掛けた後）を基準に置く"""

    def test_square_pixels(self, tmp_path, ffmpeg):
        ns = _ns(VCE_SPLIT)
        path = tmp_path / "sq.mp4"
        subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi",
                        "-i", f"color=c=gray:s={W}x{H}:r=15:d=1",
                        "-frames:v", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(path)], check=True)
        assert ns["detect_display_size"](path) == (W, H, 1, 1)

    def test_missing_file_is_none_not_an_exception(self, tmp_path):
        ns = _ns(VCE_SPLIT)
        assert ns["detect_display_size"](tmp_path / "nope.mp4") is None


# ------------------------------------------------------------------ 実描画


def _project(tmp_path, ffmpeg, transform=None, title="TITLE"):
    """白い縁取りのある素材と、1 曲ぶんの .vce.json

    書き出しが混ざらないよう、呼び出しごとに別フォルダで作る。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    media = tmp_path / "src.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}:r=15:d=4",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-shortest", "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=6",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)],
        check=True)

    source = {"path": "src.mp4"}
    if transform:
        source["transform"] = transform
    project = tmp_path / "p.vce.json"
    project.write_text(json.dumps({
        "version": "1.0",
        "sources": [source],
        "chapters": [{"local_time_ms": 0, "source_index": 0, "title": title}],
    }, ensure_ascii=False), encoding="utf-8")
    return project


def _split(project, *extra):
    out_dir = project.parent / "out"
    result = subprocess.run(
        [sys.executable, str(VCE_SPLIT), str(project), "-o", str(out_dir), *extra],
        capture_output=True, text=True, cwd=str(project.parent))
    assert result.returncode == 0, result.stderr[-2000:]
    files = sorted(out_dir.glob("*.mp4"))
    assert files, f"出力が無い: {result.stdout[-1500:]}"
    return files[0]


def _quadrants(ffmpeg, video, tmp_path, name):
    """1 フレームの四分割それぞれの「地（灰 128）からの外れ量」

    字は白だが `box=1:boxcolor=black@0.6` の暗い箱の上に乗るので、平均輝度は
    むしろ**下がる**。明るさで見ると判定を取り違えるため、地からの距離で測る。
    """
    frame = tmp_path / f"{name}.pgm"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", "1", "-i", str(video),
                    "-frames:v", "1", "-pix_fmt", "gray", str(frame)], check=True)
    raw = frame.read_bytes()
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

    def mean(x0, x1, y0, y1):
        total = sum(abs(data[y * w + x] - 128)
                    for y in range(y0, y1) for x in range(x0, x1))
        return total / max(1, (x1 - x0) * (y1 - y0))

    return {
        "bottom_left":  mean(0, w // 2, h // 2, h),
        "bottom_right": mean(w // 2, w, h // 2, h),
        "top_left":     mean(0, w // 2, 0, h // 2),
        "top_right":    mean(w // 2, w, 0, h // 2),
        "size": (w, h),
    }


KEYSTONE = {"quad": [[40, 20], [W - 60, 8], [28, H - 40], [W - 48, H - 12]],
            "reference": [W, H]}


class TestBurnedIn:
    def test_transform_changes_the_picture(self, tmp_path, ffmpeg):
        """補正が実際に掛かること（以前は開くことすらできなかった）"""
        plain = _quadrants(ffmpeg, _split(_project(tmp_path / "a", ffmpeg)),
                           tmp_path, "plain")
        warped = _quadrants(
            ffmpeg, _split(_project(tmp_path / "b", ffmpeg, transform=KEYSTONE)),
            tmp_path, "warped")
        # 白い縁取りが引き伸ばされるので、どこかの象限の明るさが必ず変わる
        assert any(abs(plain[k] - warped[k]) > 1.0
                   for k in ("bottom_left", "bottom_right", "top_left", "top_right")), \
            f"補正が効いていない: {plain} → {warped}"

    def test_output_keeps_the_frame_size(self, tmp_path, ffmpeg):
        """perspective は出力寸法を変えない"""
        q = _quadrants(ffmpeg, _split(_project(tmp_path / "c", ffmpeg, transform=KEYSTONE)),
                       tmp_path, "size")
        assert q["size"] == (W, H)

    def test_title_lands_bottom_left_by_default(self, tmp_path, ffmpeg):
        q = _quadrants(ffmpeg, _split(_project(tmp_path / "d", ffmpeg), "--overlay-title"),
                       tmp_path, "bl")
        assert q["bottom_left"] > q["top_left"] and q["bottom_left"] > q["bottom_right"]

    def test_position_flag_moves_it(self, tmp_path, ffmpeg):
        q = _quadrants(ffmpeg,
                       _split(_project(tmp_path / "e", ffmpeg), "--overlay-title",
                              "--overlay-position", "top-right"),
                       tmp_path, "tr")
        assert q["top_right"] > q["bottom_left"]

    def test_transform_and_title_together(self, tmp_path, ffmpeg):
        """両方かけても落ちないこと。字は補正の後に乗るので歪まない"""
        video = _split(_project(tmp_path / "f", ffmpeg, transform=KEYSTONE),
                       "--overlay-title")
        q = _quadrants(ffmpeg, video, tmp_path, "both")
        assert q["size"] == (W, H)
        assert q["bottom_left"] > q["top_left"]

    def test_audio_only_ignores_the_transform(self, tmp_path, ffmpeg):
        """音声のみの書き出しで補正が邪魔をしないこと"""
        project = _project(tmp_path / "g", ffmpeg, transform=KEYSTONE)
        out_dir = project.parent / "out"
        result = subprocess.run(
            [sys.executable, str(VCE_SPLIT), str(project), "-o", str(out_dir),
             "--audio-only"],
            capture_output=True, text=True, cwd=str(project.parent))
        assert result.returncode == 0, result.stderr[-1500:]
        assert sorted(out_dir.glob("*.mp3"))


class TestParityWithVceEncode:
    """同じプロジェクトから作った 2 つの成果物で、幾何が食い違わないこと"""

    def test_same_quad_is_sent_to_ffmpeg(self):
        enc, spl = _ns(VCE_ENCODE), _ns(VCE_SPLIT)
        t_enc = enc["Transform"].from_dict(KEYSTONE)
        t_spl = spl["Transform"].from_dict(KEYSTONE)
        assert t_enc.filter_str(W, H) == t_spl.filter_str(W, H)

    def test_same_default_position(self):
        enc, spl = _ns(VCE_ENCODE), _ns(VCE_SPLIT)
        assert enc["DEFAULT_OVERLAY_POSITION"] == spl["DEFAULT_OVERLAY_POSITION"]
