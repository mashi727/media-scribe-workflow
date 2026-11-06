"""画の幾何補正（傾き補正・台形補正）

傾き補正と台形補正を別々の仕組みにすると、両方かけたときに再標本化が 2 回になり、
実装も二重になる。傾き補正は「回した矩形の四隅を出力の四隅へ送る」射影変換の
特殊な場合でしかないので、`perspective` フィルタ 1 枚に寄せてある。

符号の向きは**実測で決めた**。右下がり 2.0° の白線を描いた素材に `rotate_deg=+2.0`
をかけると勾配が 0 になることを ffmpeg で確かめてあり、その回帰を
`TestAgainstFfmpeg` が持っている。幾何の符号は机上では取り違えやすく、
取り違えると補正が倍に効く（実測で +4.000° になった）ので、ここは実描画で守る。
"""

import ast
import math
import pathlib
import shutil
import subprocess
import sys

import pytest

VCE_ENCODE = pathlib.Path(__file__).resolve().parents[1] / "bin" / "vce-encode"

W, H = 1280, 720


@pytest.fixture(scope="module")
def vce():
    """bin/vce-encode からモジュール直下の定義だけを取り出して評価する

    拡張子が無いスクリプトなので import できない（既存テストと同じ手口）。
    """
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


def _bbox(quad):
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return min(xs), min(ys), max(xs), max(ys)


class TestRectForRotation:
    """傾けて枠に収まる最大の矩形"""

    def test_zero_degree_is_the_whole_frame(self, vce):
        w, h = vce["rect_for_rotation"](W, H, 0.0)
        assert (round(w), round(h)) == (W, H)

    def test_sign_does_not_matter(self, vce):
        assert vce["rect_for_rotation"](W, H, 3.0) == vce["rect_for_rotation"](W, H, -3.0)

    def test_keeps_aspect(self, vce):
        w, h = vce["rect_for_rotation"](W, H, 2.5)
        assert w / h == pytest.approx(W / H)

    @pytest.mark.parametrize("deg", [0.5, 1.0, 2.0, 5.0, 10.0])
    def test_fits_in_the_frame(self, deg, vce):
        """回したあとのバウンディングボックスが枠を超えないこと"""
        w, h = vce["rect_for_rotation"](W, H, deg)
        t = math.radians(deg)
        bw = w * abs(math.cos(t)) + h * abs(math.sin(t))
        bh = w * abs(math.sin(t)) + h * abs(math.cos(t))
        assert bw <= W + 1e-6 and bh <= H + 1e-6

    def test_larger_angle_crops_more(self, vce):
        areas = [math.prod(vce["rect_for_rotation"](W, H, d)) for d in (0, 1, 2, 5, 10)]
        assert areas == sorted(areas, reverse=True)


class TestQuadForRotation:
    """取り込み四角形"""

    def test_four_points_inside_the_frame(self, vce):
        quad = vce["quad_for_rotation"](W, H, 2.0)
        assert len(quad) == 4
        x0, y0, x1, y1 = _bbox(quad)
        assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= W + 1e-6 and y1 <= H + 1e-6

    def test_centered(self, vce):
        quad = vce["quad_for_rotation"](W, H, 3.0)
        cx = sum(p[0] for p in quad) / 4
        cy = sum(p[1] for p in quad) / 4
        assert cx == pytest.approx(W / 2) and cy == pytest.approx(H / 2)

    def test_corner_order_is_tl_tr_bl_br(self, vce):
        """perspective の引数順（左上・右上・**左下**・右下）であること

        時計回りと取り違えると画が裏返る。
        """
        tl, tr, bl, br = vce["quad_for_rotation"](W, H, 0.0)
        assert tl[0] < tr[0] and bl[0] < br[0]       # 左右
        assert tl[1] < bl[1] and tr[1] < br[1]       # 上下

    def test_positive_degree_samples_a_right_descending_edge(self, vce):
        """正の角度は「右下がりの水平線」を拾いにいく

        素材が右下がりなら、その線に沿って取り込めば出力は水平になる。
        TestAgainstFfmpeg が実描画で裏を取っている。
        """
        tl, tr, _, _ = vce["quad_for_rotation"](W, H, 2.0)
        assert tr[1] > tl[1]


class TestTransformFromDict:
    """プロジェクトからの読み取り"""

    def test_none_is_none(self, vce):
        assert vce["Transform"].from_dict(None) is None
        assert vce["Transform"].from_dict({}) is None

    def test_rotation_only(self, vce):
        t = vce["Transform"].from_dict({"rotate_deg": -1.4})
        assert t.rotate_deg == -1.4 and t.quad is None and not t.is_identity

    def test_zero_rotation_is_identity(self, vce):
        assert vce["Transform"].from_dict({"rotate_deg": 0}).is_identity

    def test_quad(self, vce):
        t = vce["Transform"].from_dict(
            {"quad": [[0, 0], [100, 0], [0, 50], [100, 50]], "reference": [200, 100]})
        assert t.quad[1] == (100.0, 0.0) and t.reference == (200, 100)

    @pytest.mark.parametrize("bad", [
        {"quad": [[0, 0], [1, 1], [2, 2]]},              # 3 点
        {"quad": [[0, 0], [1, 1], [2, 2], [3]]},         # 座標が 1 つ
        {"reference": [1920]},                           # 幅だけ
        {"interpolation": "lanczos"},                    # 対応外
    ])
    def test_rejects_broken_input(self, bad, vce):
        with pytest.raises(ValueError):
            vce["Transform"].from_dict(bad)


class TestResolveQuad:
    def test_reference_is_scaled_to_the_actual_source(self, vce):
        """別解像度で測った四隅を比例で読み替える

        GUI で 1920x1080 のプレビュー上に置いた点を、3840x2160 の素材へ当てる場面。
        """
        t = vce["Transform"](quad=[(0, 0), (960, 0), (0, 540), (960, 540)],
                             reference=(1920, 1080))
        assert t.resolve_quad(3840, 2160) == [(0, 0), (1920, 0), (0, 1080), (1920, 1080)]

    def test_same_resolution_is_untouched(self, vce):
        quad = [(10, 20), (100, 20), (10, 200), (100, 200)]
        t = vce["Transform"](quad=quad, reference=(W, H))
        assert t.resolve_quad(W, H) == quad


class TestFilterString:
    def test_sense_is_source(self, vce):
        """sense を取り違えると補正が反対にかかる"""
        f = vce["Transform"](rotate_deg=2.0).filter_str(W, H)
        assert "sense=source" in f and f.startswith("perspective=")

    def test_names_all_eight_coordinates(self, vce):
        f = vce["Transform"](rotate_deg=2.0).filter_str(W, H)
        for name in ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"):
            assert f"{name}=" in f

    def test_interpolation_is_carried(self, vce):
        f = vce["Transform"](rotate_deg=1.0, interpolation="cubic").filter_str(W, H)
        assert "interpolation=cubic" in f


pytestmark_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg が無い")


@pytestmark_ffmpeg
class TestAgainstFfmpeg:
    """実際に描いて確かめる

    幾何の符号は机上で取り違えやすい。素材の傾きを既知にして、補正後の勾配を測る。
    """

    @staticmethod
    def _render(tmp_path, source_vf, vf=None):
        import numpy as np

        src = tmp_path / "src.png"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", f"color=c=black:s={W}x{H}:d=1", "-vf", source_vf,
             "-frames:v", "1", str(src)], check=True)
        out = tmp_path / "out.gray"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-f", "rawvideo", "-pix_fmt", "gray", str(out)]
        subprocess.run(cmd, check=True)
        return np.frombuffer(out.read_bytes(), dtype=np.uint8).reshape(H, W).astype(float)

    @staticmethod
    def _slope(frame):
        """白線の勾配（1px 進むごとの y の増分。正が右下がり）"""
        import numpy as np

        xs, ys = [], []
        for x in range(0, W, 8):
            col = frame[:, x]
            if col.max() < 100:
                continue
            weight = np.clip(col - 60, 0, None)
            ys.append((weight * np.arange(H)).sum() / weight.sum())
            xs.append(x)
        assert len(xs) >= 10, "白線が見つからない"
        return float(np.polyfit(xs, ys, 1)[0])

    @pytest.mark.parametrize("tilt", [2.0, -1.5])
    def test_positive_degree_levels_a_right_descending_line(self, tilt, tmp_path, vce):
        """傾き tilt の線は rotate_deg=tilt で水平になる"""
        slope = math.tan(math.radians(tilt))
        source_vf = (f"geq=lum='if(lt(abs(Y-(360+{slope:.6f}*(X-640))),2.5),255,0)'"
                     f":cb=128:cr=128")

        before = self._slope(self._render(tmp_path, source_vf))
        assert math.degrees(math.atan(before)) == pytest.approx(tilt, abs=0.05)

        f = vce["Transform"](rotate_deg=tilt).filter_str(W, H)
        after = self._slope(self._render(tmp_path, source_vf, f))
        assert abs(after) < 0.002, f"補正後も傾いている（勾配 {after:+.5f}）"

    def test_no_blank_corners(self, tmp_path, vce):
        """四隅が空かないこと

        取り込み四角形が枠の内側にあるので、補正後も全面が素材で埋まる。
        """
        f = vce["Transform"](rotate_deg=2.0).filter_str(W, H)
        frame = self._render(tmp_path, "geq=lum=255:cb=128:cr=128", f)
        assert frame.min() > 200

    def test_aspect_is_preserved(self, tmp_path, vce):
        """円が楕円にならないこと（縦横比が崩れていない）"""
        circle = "geq=lum='if(lt((X-640)^2+(Y-360)^2,120^2),255,0)':cb=128:cr=128"
        import numpy as np

        f = vce["Transform"](rotate_deg=2.0).filter_str(W, H)
        frame = self._render(tmp_path, circle, f)
        ys, xs = np.where(frame > 128)
        assert (xs.max() - xs.min()) / (ys.max() - ys.min()) == pytest.approx(1.0, abs=0.02)

    def test_keystone_fills_the_frame(self, tmp_path, vce):
        """台形に写った被写体を四隅指定で起こすと全面を埋める

        縁 1px は補間の境界なので、面積比で見る。
        """
        poly = ("geq=lum='if(between(Y,160,560)*"
                "gt(X, 440-(200*(Y-160)/400))*lt(X, 840+(200*(Y-160)/400)),255,0)'"
                ":cb=128:cr=128")
        t = vce["Transform"](quad=[(440, 160), (840, 160), (240, 560), (1040, 560)])
        frame = self._render(tmp_path, poly, t.filter_str(W, H))
        assert (frame > 128).mean() > 0.99


@pytestmark_ffmpeg
class TestEndToEnd:
    """vce-encode を実際に通す

    幾何そのものはユニットで守れるが、「補正が出力まで届くか」は別の話。
    実装時、区間がソース全体を覆うプロジェクトでは `can_skip` の高速パスが
    再エンコードを省くため、**補正が黙って効かなかった**。ユニットは全て
    通っていたので、この経路は実際に通さないと守れない。
    """

    @staticmethod
    def _build(tmp_path, tilt):
        import json

        w, h = 320, 180
        slope = math.tan(math.radians(tilt))
        src = tmp_path / "src.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r=15:d=2",
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-vf", f"geq=lum='if(lt(abs(Y-({h//2}+{slope:.6f}*(X-{w//2}))),2.0),255,0)'"
                    f":cb=128:cr=128",
             "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             str(src)], check=True)
        project = tmp_path / "p.vce.json"
        project.write_text(json.dumps({
            "version": "1.0",
            "sources": [{"path": "src.mp4", "transform": {"rotate_deg": tilt}}],
            "chapters": [{"local_time_ms": 0, "source_index": 0, "title": "A"}],
        }, ensure_ascii=False), encoding="utf-8")
        return project, (w, h)

    @staticmethod
    def _tilt_of(path, size):
        import numpy as np

        w, h = size
        raw = path.parent / "probe.gray"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(path),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(raw)], check=True)
        frame = np.frombuffer(raw.read_bytes(), dtype=np.uint8).reshape(h, w).astype(float)
        xs, ys = [], []
        for x in range(0, w, 4):
            col = frame[:, x]
            if col.max() < 100:
                continue
            weight = np.clip(col - 60, 0, None)
            ys.append((weight * np.arange(h)).sum() / weight.sum())
            xs.append(x)
        assert len(xs) >= 10, "白線が見つからない"
        return math.degrees(math.atan(float(np.polyfit(xs, ys, 1)[0])))

    def test_tilt_is_corrected_in_the_encoded_file(self, tmp_path):
        """素材全体が 1 区間でも補正が出力に届くこと（can_skip の回帰）"""
        project, size = self._build(tmp_path, 2.0)
        assert self._tilt_of(tmp_path / "src.mp4", size) == pytest.approx(2.0, abs=0.15)

        subprocess.run([sys.executable, str(VCE_ENCODE), str(project)],
                       check=True, capture_output=True)
        out = tmp_path / "p.vce_encoded.mp4"
        assert out.exists(), "出力が無い"
        assert abs(self._tilt_of(out, size)) < 0.25

    def test_plain_string_sources_still_work(self, tmp_path):
        """旧形式（相対パスの文字列）のプロジェクトが無改修で通ること"""
        import json

        project, size = self._build(tmp_path, 0.0)
        project.write_text(json.dumps({
            "version": "1.0",
            "sources": ["src.mp4"],
            "chapters": [{"local_time_ms": 0, "source_index": 0, "title": "A"}],
        }, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(VCE_ENCODE), str(project), "--dry-run"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "transform" not in r.stdout
