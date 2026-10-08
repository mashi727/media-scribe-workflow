"""
test_vce_encode_srt_remap.py - SRT の時刻をカットへ追従させる

文字起こしをカット前に行い、ここで時刻を付け替える。カット後の音声を起こすと
継ぎ目で ASR の文脈が壊れるのに対し、カット前なら音声が連続しており、
付け替えは確定値（calculate_extraction_plan が返す SegmentInfo）による算術なので
誤差が入らない。チャプターと同じ写像を使うので両者がずれようがない。
"""

import ast
import pathlib

import pytest

VCE_ENCODE = pathlib.Path(__file__).resolve().parents[1] / "bin" / "vce-encode"


@pytest.fixture(scope="module")
def vce():
    """bin/vce-encode から、モジュール直下の定義だけを取り出して評価する

    拡張子が無いスクリプトなので import できない。巨大なクラスと main は
    読み込まず、純粋関数とデータクラスだけを見る。
    """
    tree = ast.parse(VCE_ENCODE.read_text(encoding="utf-8"))
    keep = [
        n for n in tree.body
        if not (isinstance(n, ast.ClassDef) and n.name == "ProjectEncoder")
        and not (isinstance(n, ast.FunctionDef) and n.name == "main")
        and not isinstance(n, ast.If)
    ]
    namespace: dict = {"__name__": "vce"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(VCE_ENCODE), "exec"), namespace)
    return namespace


@pytest.fixture
def segments(vce):
    """実素材と同じ形: 途中の休憩と末尾を落とす2区間"""
    SegmentInfo = vce["SegmentInfo"]
    return [
        SegmentInfo(0, 0, 5_717_499, 0),                      # 0 - 1:35:17.499
        SegmentInfo(0, 6_719_036, 12_264_736, 5_717_499),     # 1:51:59.036 - 3:24:24.736
    ]


def _cue(vce, start, end, text="x"):
    return vce["SrtCue"](1, start, end, text)


class TestParseAndFormat:
    @pytest.mark.parametrize("text,ms", [
        ("00:00:00,000", 0),
        ("00:01:02,345", 62_345),
        ("01:35:17,499", 5_717_499),
        ("00:00:01.5", 1_500),      # 小数点とミリ秒1桁も読む
    ])
    def test_parse(self, vce, text, ms):
        assert vce["parse_srt_time"](text) == ms

    def test_roundtrip(self, vce):
        for ms in (0, 1, 999, 5_717_499, 12_264_736):
            assert vce["parse_srt_time"](vce["format_srt_time"](ms)) == ms


class TestRemap:
    def test_before_the_cut_is_shifted_by_zero(self, vce, segments):
        out = vce["remap_srt_cues"]([_cue(vce, 600_000, 604_000)], segments)
        assert (out[0].start_ms, out[0].end_ms) == (600_000, 604_000)

    def test_after_the_cut_is_shifted_back(self, vce, segments):
        out = vce["remap_srt_cues"]([_cue(vce, 6_719_500, 6_723_500)], segments)
        shift = 6_719_036 - 5_717_499
        assert out[0].start_ms == 6_719_500 - shift

    def test_inside_a_cut_is_dropped(self, vce, segments):
        assert vce["remap_srt_cues"]([_cue(vce, 6_000_000, 6_004_000)], segments) == []

    def test_after_the_final_cut_is_dropped(self, vce, segments):
        assert vce["remap_srt_cues"]([_cue(vce, 12_300_000, 12_304_000)], segments) == []

    def test_straddling_cue_is_clipped(self, vce, segments):
        """境界を跨ぐ cue は保持側へ切り詰める（カットで発話が切れるのだから正しい）"""
        out = vce["remap_srt_cues"]([_cue(vce, 5_715_000, 5_719_000)], segments)
        assert len(out) == 1
        assert out[0].end_ms == 5_717_499

    def test_cue_spanning_two_segments_is_split(self, vce, segments):
        out = vce["remap_srt_cues"]([_cue(vce, 5_700_000, 6_730_000)], segments)
        assert len(out) == 2, "保持区間ごとに分かれること"
        assert out[0].end_ms <= out[1].start_ms

    def test_tiny_remainder_is_dropped(self, vce, segments):
        """切り詰めた残りが短すぎるものは捨てる（1フレーム未満の cue を作らない）"""
        out = vce["remap_srt_cues"]([_cue(vce, 5_717_400, 5_800_000)], segments)
        assert out == []

    @pytest.mark.parametrize("length", [0, 100, 199])
    def test_short_uncut_cue_is_kept(self, vce, segments, length):
        """切り詰めていない cue は短くても残す（kotoba は 0〜0.2 秒の cue を出し、本文がある。
        一律に捨てていたため 2026-10 の素材で kotoba の 5〜7% が消えていた）"""
        out = vce["remap_srt_cues"]([_cue(vce, 600_000, 600_000 + length, "本文")], segments)
        assert [(c.start_ms, c.end_ms, c.text) for c in out] == [(600_000, 600_000 + length, "本文")]

    def test_short_uncut_cue_after_the_cut_is_kept_and_shifted(self, vce, segments):
        out = vce["remap_srt_cues"]([_cue(vce, 6_800_000, 6_800_050)], segments)
        shift = 6_719_036 - 5_717_499
        assert [(c.start_ms, c.end_ms) for c in out] == [(6_800_000 - shift, 6_800_050 - shift)]

    def test_indices_are_renumbered_in_order(self, vce, segments):
        cues = [_cue(vce, 600_000, 604_000), _cue(vce, 6_719_500, 6_723_500)]
        out = vce["remap_srt_cues"](cues, segments)
        assert [c.index for c in out] == [1, 2]
        assert out[0].start_ms < out[1].start_ms


class TestRoundTripThroughFiles:
    def test_parse_write_parse(self, vce, tmp_path, segments):
        src = tmp_path / "in.srt"
        src.write_text(
            "1\n00:10:00,000 --> 00:10:04,000\nこんにちは\n\n"
            "2\n01:40:00,000 --> 01:40:04,000\nカット区間\n\n"
            "3\n01:52:00,000 --> 01:52:04,000\n休憩明け\n",
            encoding="utf-8",
        )
        cues = vce["parse_srt"](src)
        assert len(cues) == 3
        out = vce["remap_srt_cues"](cues, segments)
        assert len(out) == 2, "カット区間の1件が落ちること"

        dest = tmp_path / "out.srt"
        vce["write_srt"](out, dest)
        again = vce["parse_srt"](dest)
        assert [(c.start_ms, c.end_ms, c.text) for c in again] == \
               [(c.start_ms, c.end_ms, c.text) for c in out]

    def test_broken_blocks_are_skipped(self, vce, tmp_path):
        """ASR の出力は時々崩れる。1ブロック壊れても全部を失わない"""
        src = tmp_path / "broken.srt"
        src.write_text(
            "1\nこれは時刻行ではない\n本文\n\n"
            "2\n00:00:05,000 --> 00:00:06,000\n生きている\n",
            encoding="utf-8",
        )
        cues = vce["parse_srt"](src)
        assert len(cues) == 1
        assert cues[0].text == "生きている"


class TestDiscovery:
    def test_finds_engine_outputs_next_to_the_source(self, vce, tmp_path):
        """transcribe-srt は <base>_srt/<base>_<engine>.srt へ出す"""
        source = tmp_path / "take.wav"
        source.write_bytes(b"x")
        (tmp_path / "take_srt").mkdir()
        for name in ("take_wp.srt", "take_kotoba.num.srt", "take_dg.srt"):
            (tmp_path / "take_srt" / name).write_text("", encoding="utf-8")
        (tmp_path / "unrelated.srt").write_text("", encoding="utf-8")

        found = {p.name for p in vce["find_source_srts"](source)}
        assert found == {"take_wp.srt", "take_kotoba.num.srt", "take_dg.srt"}

    def test_none_when_absent(self, vce, tmp_path):
        source = tmp_path / "take.wav"
        source.write_bytes(b"x")
        assert vce["find_source_srts"](source) == []
