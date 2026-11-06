"""
test_vce_split_drop_excluded.py - '--' 区間（MC・CM）の扱い

既定では '--' 区間は直前のチャプターに含まれ、各曲は次の有効チャプターまで続く。
--drop-excluded では '--' の開始点で切り、その区間を出力から落とす。
ライブ収録を曲ごとに切り出すとき、MC を曲に含めないために使う。
"""

import ast
import pathlib

import pytest

VCE_SPLIT = pathlib.Path(__file__).resolve().parents[1] / "bin" / "vce-split"


@pytest.fixture(scope="module")
def vce():
    """bin/vce-split から main 以外の定義を取り出して評価する（拡張子が無く import できない）"""
    tree = ast.parse(VCE_SPLIT.read_text(encoding="utf-8"))
    keep = [
        n for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name == "main")
        and not isinstance(n, ast.If)
    ]
    namespace: dict = {"__name__": "vce", "__file__": str(VCE_SPLIT)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(VCE_SPLIT), "exec"), namespace)
    return namespace


def _splitter(vce, chapters, durations):
    """__init__ はファイルを読むので通さず、章とソースだけを差し込む"""
    sp = object.__new__(vce["ProjectSplitter"])
    sp.chapters = [vce["ChapterInfo"](local_time_ms=t, title=title, source_index=s)
                   for t, title, s in chapters]
    sp.sources = [vce["SourceFile"](path=pathlib.Path(f"src{i}.mp4"), duration_ms=d)
                  for i, d in enumerate(durations)]
    return sp


# 実素材と同じ形: 曲・MC・曲・つづき・曲・末尾の休憩
LIVE = [
    (158_726, "01_江差恋女FC", 0),
    (414_930, "--MC", 0),
    (859_142, "02_知床岬2C", 0),
    (1_065_651, "--つづき", 0),
    (1_070_480, "03_ザンザ岬2C", 0),
    (6_570_205, "--休憩", 0),
]
DURATION = 6_934_354


def _ranges(segments):
    return [(start, end, title) for _, start, end, title, _ in segments]


def test_default_merges_excluded_into_previous(vce):
    sp = _splitter(vce, LIVE, [DURATION])
    assert _ranges(sp.get_chapter_segments()) == [
        (158_726, 859_142, "01_江差恋女FC"),
        (859_142, 1_070_480, "02_知床岬2C"),
        (1_070_480, DURATION, "03_ザンザ岬2C"),
    ]


def test_drop_excluded_cuts_at_excluded_start(vce):
    sp = _splitter(vce, LIVE, [DURATION])
    assert _ranges(sp.get_chapter_segments(drop_excluded=True)) == [
        (158_726, 414_930, "01_江差恋女FC"),
        (859_142, 1_065_651, "02_知床岬2C"),
        (1_070_480, 6_570_205, "03_ザンザ岬2C"),
    ]


def test_drop_excluded_keeps_last_chapter_to_end(vce):
    sp = _splitter(vce, LIVE[:3], [DURATION])
    assert _ranges(sp.get_chapter_segments(drop_excluded=True))[-1] == (
        859_142, DURATION, "02_知床岬2C")


def test_drop_excluded_multi_source(vce):
    chapters = [
        (0, "A", 0),
        (60_000, "--MC", 0),
        (90_000, "B", 0),
        (0, "C", 1),
        (30_000, "--CM", 1),
    ]
    sp = _splitter(vce, chapters, [120_000, 50_000])
    assert _ranges(sp.get_chapter_segments(drop_excluded=True)) == [
        (0, 60_000, "A"),
        (90_000, 120_000, "B"),
        (0, 30_000, "C"),
    ]
    assert _ranges(sp.get_chapter_segments()) == [
        (0, 90_000, "A"),
        (90_000, 120_000, "B"),
        (0, 50_000, "C"),
    ]
