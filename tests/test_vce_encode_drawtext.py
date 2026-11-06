"""
test_vce_encode_drawtext.py - vce-encode の drawtext エスケープ

実際に踏んだ不具合（いずれも曲名 `130_Isn't She Lovely`）:

1. `'` を `\\'` に置換していた頃は、引用が切れて
       ERROR: [AVFilterGraph] No such filter: '1315.718'
   で落ちていた。
2. `'\\''` で引用を閉じ・開き直す方式に変えたところ、**エラーは出ないまま
   曲名が空で描かれた**（2026-10 の合宿の動画で、130 の章だけ曲名が消えていた）。
   旧テストは「ffmpeg が画像を書き出したか」しか見ていなかったので、これを通した。

そこで本テストは、同じ文字列を `textfile`（エスケープ不要）で描いた画像を正解とし、
エスケープ版の画像が**画素単位で一致するか**で判定する。

bin/vce-encode はスクリプト（拡張子なし）なので、関数定義部だけを読み込む。
"""

import pathlib
import shutil
import subprocess

import pytest

VCE_ENCODE = pathlib.Path(__file__).resolve().parents[1] / "bin" / "vce-encode"
SIZE = "1200x80"


@pytest.fixture(scope="module")
def escape_drawtext():
    src = VCE_ENCODE.read_text(encoding="utf-8")
    namespace: dict = {"__file__": str(VCE_ENCODE)}
    exec(compile(src.split("def main(")[0], str(VCE_ENCODE), "exec"), namespace)
    return namespace["escape_drawtext"]


# 実際の呼び出しと同じ形（text='...':expansion=none、enable 付きで他の drawtext と連結）
def _vf_escaped(escaped, tail):
    return (f"drawtext=text='{escaped}':expansion=none:fontsize=32:fontcolor=white:"
            f"x=10:y=20:enable='between(t,0,5)'," + tail)


def _vf_reference(textfile, tail):
    return (f"drawtext=textfile='{textfile}':expansion=none:fontsize=32:fontcolor=white:"
            f"x=10:y=20," + tail)


TAIL = "drawtext=text='next':fontsize=10:fontcolor=gray:x=1:y=1"


def _frame(vf, out):
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={SIZE}:r=1:d=1",
         "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    return out.read_bytes() if r.returncode == 0 and out.exists() else None


pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg が無い")


HOSTILE = [
    "130_Isn't She Lovely",            # 空で描かれていた
    "Isn't 0:10 混在",                  # ' と :
    "Isn't [角括弧] 100%の達成",          # ' と [ ] %
    "It's a, b; c",                    # ' と , ;
    "back\\slash",                     # 引用の内側に残す方式では崩れた
    "Don't \\ stop",
    "100%の達成",                       # expansion=normal だと崩れる
    "%{pts}",                          # 展開されてはいけない
    "A:B の区切り",
    "[角括弧]",
    "067_人生のメリーゴーランド（Take2）",
    "080_レオケの新世界交響曲（86〜）",
    "131_未来予想図Ⅱ",
    "普通のタイトル",
]


@pytest.fixture(scope="module")
def vce_ns():
    """bin/vce-encode のモジュール直下の定義を評価する"""
    import ast

    tree = ast.parse(VCE_ENCODE.read_text(encoding="utf-8"))
    keep = [
        n for n in tree.body
        if not (isinstance(n, ast.ClassDef) and n.name == "ProjectEncoder")
        and not (isinstance(n, ast.FunctionDef) and n.name == "main")
        and not isinstance(n, ast.If)
    ]
    ns: dict = {"__file__": str(VCE_ENCODE)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(VCE_ENCODE), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def builder(vce_ns):
    """章名 1 つを実際の生成器に通して drawtext 文字列を返す"""
    def build(title):
        chapters = [vce_ns["ChapterInfo"](local_time_ms=0, title=title, source_index=0)]
        out = vce_ns["build_title_overlays"](chapters, "/noexist.ttf", "bottom-left",
                                            0, 5000, 5000)
        assert len(out) == 1
        return out[0]
    return build


class TestGeneratedFilter:
    """焼き込みの生成器が吐く drawtext を、textfile 版と画素で突き合わせる

    エスケープ関数だけを単体で見ても、**呼び出し側の組み立て**が崩れると
    無言で空描画になる。生成器を通した実物で見る。
    """

    @pytest.mark.parametrize("title", HOSTILE)
    def test_generated_filter_draws_exactly_the_title(self, builder, title, tmp_path):
        import re

        tf = tmp_path / "title.txt"
        tf.write_text(title, encoding="utf-8")
        ref = _frame(_vf_reference(tf, TAIL), tmp_path / "ref.raw")
        assert ref is not None, "正解側の描画に失敗（テスト環境の問題）"
        assert any(b > 128 for b in ref), "正解側に文字が描かれていない（フォント環境）"

        # 生成器の出力から、位置・体裁だけを正解側と揃える（比べたいのは文字）
        generated = builder(title)
        text_opt = re.search(r"text=(''.*?''|'.*?'):expansion=none", generated)
        assert text_opt, f"text= を取り出せない: {generated}"
        vf = (f"drawtext=text={text_opt.group(1)}:expansion=none:fontsize=32:"
              f"fontcolor=white:x=10:y=20:enable='between(t,0,5)'," + TAIL)
        got = _frame(vf, tmp_path / "got.raw")
        assert got is not None, f"フィルタが壊れる: {title!r}"
        assert got == ref, f"描かれた文字が違う（空・欠け・化け）: {title!r}"


class TestEscapeDrawtext:
    @pytest.mark.parametrize("title", HOSTILE)
    def test_draws_exactly_the_title(self, escape_drawtext, title, tmp_path):
        """エスケープ版の描画が、textfile で描いた正解と画素単位で一致する"""
        tf = tmp_path / "title.txt"
        tf.write_text(title, encoding="utf-8")
        ref = _frame(_vf_reference(tf, TAIL), tmp_path / "ref.raw")
        got = _frame(_vf_escaped(escape_drawtext(title), TAIL), tmp_path / "got.raw")
        assert ref is not None, "正解側の描画に失敗（テスト環境の問題）"
        assert got is not None, f"フィルタが壊れる: {title!r}"
        assert any(b > 128 for b in ref), "正解側に文字が描かれていない（フォント環境の問題）"
        assert got == ref, f"描かれた文字が違う（空・欠け・化け）: {title!r}"

    def test_caller_disables_expansion(self, builder):
        """% と \\ を文字どおり描くには、呼び出し側の expansion=none が要る

        以前はソース文字列の完全一致で見ていたが、生成を
        `build_title_overlays` に寄せた際に形だけ変わって落ちた。意図は
        「生成されるフィルタに expansion=none が入っていること」なので、
        **生成結果を見る**ように改めた。
        """
        out = builder("100%の達成")
        assert "expansion=none" in out

    def test_caller_wraps_the_escaped_value_in_quotes(self, builder):
        """`text=''…''` の二重引用を保つこと

        `escape_drawtext` は自分で `'…'` を付けて返す。呼び出し側が囲むのを
        やめると、`'` を含む曲名がエラー無しで空描画になる（2026-10 に
        実際に起きた壊れ方）。
        """
        out = builder("Isn't She Lovely")
        assert "text=''" in out

    def test_closes_the_quote_itself(self, escape_drawtext):
        """呼び出し側の text='...' と合わせて text=''<本体>'' になる構造"""
        out = escape_drawtext("Isn't")
        assert out.startswith("'") and out.endswith("'")

    def test_whole_chapter_set_renders(self, escape_drawtext, tmp_path):
        """実際の章立てに近い件数をまとめて連結しても通ること"""
        titles = [
            "001_Opening Tune_2025",
            "130_Isn't She Lovely",
            "130_Isn't She Lovely（33手前のアウフタクト）",
            "131_未来予想図II",
            "休憩明け",
            "132_名探偵コナン メイン・テーマ",
            "047_An Affair to Remember",
            "終了時の連絡事項",
        ]
        vf = ",".join(
            f"drawtext=text='{escape_drawtext(t)}':expansion=none:fontsize=24:fontcolor=white:"
            f"x=10:y=10:enable='between(t,{i},{i + 1})'"
            for i, t in enumerate(titles))
        assert _frame(vf, tmp_path / "all.raw") is not None
