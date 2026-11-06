"""vce-encode / vce-split で共有する幾何補正とタイトル焼き込み

**同じ式を 2 本のスクリプトに置かない。** 片方だけ直すと「1 本にまとめた版と
曲ごとに分けた版で絵が違う」という、気づくのに最も時間のかかる壊れ方をする。
出どころをここ 1 つにして、`bin/vce-encode` と `bin/vce-split` の両方が読む。

chaptr 側（`chaptr/pipeline/geometry.py`）にも同じ式がある。こちらはリポジトリが
分かれているため実装を共有できないので、両者で一致すべき値を
`tests/test_vce_encode_transform.py` と chaptr の `tests/test_geometry.py` に
固定してある。
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def escape_drawtext(text: str) -> str:
    r"""drawtext の text= に渡す値をエスケープする

    呼び出し側は結果を ``text='...'`` と単引用で囲み、``expansion=none`` を付ける。
    この関数は自分で引用を閉じて ``'<本体>'`` を返すので、最終的には
    ``text=''<本体>''`` となり、本体は**引用の外**で解釈される。

    ffmpeg は値を2回ほどく（drawtext のオプション → フィルタグラフ）ので、
    内側から順に2段エスケープする。

    1. オプション段: ``\`` ``'`` ``:``
    2. フィルタグラフ段: ``\`` ``'`` ``[`` ``]`` ``,`` ``;``

    経緯（2026-10 に実測で特定）:

    - ``'\''`` で引用を閉じて開き直す旧方式は、**エラーを出さずに空文字を描いた**。
      ``130_Isn't She Lovely`` の章だけ曲名が消えていた。``\'`` に置換するさらに
      前の方式は ``No such filter: '1315.718'`` で落ちていた。
    - 引用の内側に残す方式は、``\`` を含む曲名を正しく描けなかった。
    - ``%`` と ``\`` は drawtext の既定（``expansion=normal``）で展開用の記号として
      読まれる。呼び出し側の ``expansion=none`` と組で、文字どおりに描かれる。

    正しさは「何か描けたか」ではなく、``textfile``（エスケープ不要）で描いた画像と
    **画素単位で一致するか**で確かめている（tests/test_vce_encode_drawtext.py）。
    前後の空白は引用の外では落ちる（チャプター名は読み込み時に strip 済み）。
    """
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    for ch in "\\'[],;":
        text = text.replace(ch, "\\" + ch)
    return "'" + text + "'"


#: タイトル焼き込みの位置 → drawtext の x / y 式
#:
#: 余白は解像度に比例させる（固定画素だと 4K で枠に貼り付く）。`tw`/`th` は
#: drawtext が持つテキストの寸法。`box=1` の枠は `boxborderw` の分だけ外へ
#: 広がるので、余白はそれを見込んで取ってある。
OVERLAY_POSITIONS = {
    "bottom-left":  ("w*0.035",         "h-th-h*0.06"),
    "bottom-right": ("w-tw-w*0.035",    "h-th-h*0.06"),
    "top-left":     ("w*0.035",         "h*0.06"),
    "top-right":    ("w-tw-w*0.035",    "h*0.06"),
    # 従来の位置。上寄りの中央で、被写体に重なりやすい
    "center":       ("(w-tw)/2",        "h*0.325-th/2"),
}

DEFAULT_OVERLAY_POSITION = "bottom-left"


def build_title_overlays(chapters: List['ChapterInfo'],
                         font_path: str,
                         position: str = DEFAULT_OVERLAY_POSITION,
                         window_start_ms: int = 0,
                         window_end_ms: Optional[int] = None,
                         fallback_end_ms: int = 0) -> List[str]:
    """章名を焼き込む drawtext を並べて返す

    `chapters` は**出力側の時間軸**（カット後）で渡す。`window_start_ms` 以降を
    切り出した映像に載せる場合は、その値を引いてフィルタ側の時刻に直す。
    セグメントごとに切り出してから結合する経路では、各セグメントの
    `output_start_ms` を渡すことで時刻が合う。

    除外章（`--` 始まり）は字を出さない。ある章の表示は次の**有効な**章まで
    続く（出力ではカット済みで隣り合うため）。
    """
    valid = sorted((c for c in chapters if not c.title.startswith("--")),
                   key=lambda c: c.local_time_ms)
    if not valid:
        return []

    if window_end_ms is None:
        window_end_ms = max(fallback_end_ms,
                            valid[-1].local_time_ms + 1)

    x_expr, y_expr = OVERLAY_POSITIONS[position]
    filters: List[str] = []
    for i, ch in enumerate(valid):
        start_ms = ch.local_time_ms
        if i + 1 < len(valid):
            end_ms = valid[i + 1].local_time_ms
        else:
            end_ms = max(window_end_ms, fallback_end_ms)

        # この映像に写る範囲だけ出す
        lo = max(start_ms, window_start_ms)
        hi = min(end_ms, window_end_ms)
        if hi <= lo:
            continue

        filters.append(
            f"drawtext=fontfile='{font_path}':"
            # `escape_drawtext` は自分で `'…'` を付けて返し、ここでもう一度囲んで
            # `text=''…''` にするのが約束（tests/test_vce_encode_drawtext.py が
            # textfile 版との画素一致で検証している）。一重にすると `'` を含む
            # 曲名がエラー無しで空描画になる。
            f"text='{escape_drawtext(ch.title)}':"
            f"expansion=none:"
            f"fontsize=56:"
            f"fontcolor=white:"
            f"borderw=2:"
            f"bordercolor=black:"
            f"box=1:"
            f"boxcolor=black@0.6:"
            f"boxborderw=15:"
            f"x={x_expr}:"
            f"y={y_expr}:"
            f"enable='between(t,{(lo - window_start_ms) / 1000.0:.3f},"
            f"{(hi - window_start_ms) / 1000.0:.3f})'"
        )
    return filters


def rect_for_rotation(width: float, height: float, deg: float,
                      aspect: Optional[float] = None) -> Tuple[float, float]:
    """枠 width×height の中へ、deg だけ傾けて収まる最大の矩形を返す

    傾き補正では「水平を出すために画を回す」ので、四隅が必ず空く。空いた分を
    捨てた後に残る最大の矩形がこれ。`aspect` を出力比に合わせておけば、
    引き伸ばしの無い（縦横比の崩れない）切り出しになる。

    中心をそろえた矩形どうしなら、回した矩形が枠に収まる条件は
    バウンディングボックスが収まることと同値なので、閉形式で出る。
        w·|cos| + h·|sin| ≤ W
        w·|sin| + h·|cos| ≤ H
    """
    if aspect is None or aspect <= 0:
        aspect = width / height
    t = math.radians(abs(deg))
    c, s_ = math.cos(t), math.sin(t)
    w = min(width / (c + s_ / aspect), height / (s_ + c / aspect))
    return w, w / aspect


def quad_for_rotation(width: float, height: float, deg: float,
                      aspect: Optional[float] = None) -> List[Tuple[float, float]]:
    """傾き補正の取り込み四角形を返す（TL, TR, BL, BR の順）

    順序は perspective フィルタの引数順（x0y0=左上, x1y1=右上, x2y2=**左下**,
    x3y3=右下）に合わせてある。時計回りではないので注意。

    符号: `deg` が正のとき、出力では画が**反時計回り**に回る。写真編集ソフトの
    角度スライダと同じ向き（右下がりの水平線は正の値で直る）。
    """
    w, h = rect_for_rotation(width, height, deg, aspect)
    cx, cy = width / 2.0, height / 2.0
    t = math.radians(deg)
    cos_t, sin_t = math.cos(t), math.sin(t)
    out = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (-w / 2, h / 2), (w / 2, h / 2)):
        out.append((cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t))
    return out


@dataclass
class Transform:
    """画の幾何補正（傾き補正・台形補正）

    `perspective` フィルタ 1 枚で表す。傾き補正は「回した矩形の四隅」を指定する
    だけの特殊な場合なので、台形補正と同じ仕組みに乗る。rotate で回してから
    perspective を足すと再標本化が 2 回になるが、この形なら常に 1 回で済む。

    - `quad` があればそれを使う（台形補正。四隅を自由に置ける）
    - 無ければ `rotate_deg` から矩形を導く（傾き補正）
    - `reference` は quad を測ったときの解像度。実素材と違えば比例で読み替える

    perspective は出力サイズを入力と同じに保つので、`calculate_target_params`
    の判定には影響しない（四隅を切り落とす rotate+crop 方式との違い）。
    """
    rotate_deg: float = 0.0
    quad: Optional[List[Tuple[float, float]]] = None
    reference: Optional[Tuple[int, int]] = None
    interpolation: str = "linear"

    INTERPOLATIONS = ("linear", "cubic")

    @property
    def is_identity(self) -> bool:
        return self.quad is None and abs(self.rotate_deg) < 1e-9

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional['Transform']:
        if not data:
            return None
        quad = data.get('quad')
        if quad is not None:
            if len(quad) != 4 or any(len(pt) != 2 for pt in quad):
                raise ValueError(
                    f"transform.quad は [x,y] を 4 点（左上・右上・左下・右下）: {quad!r}")
            quad = [(float(x), float(y)) for x, y in quad]
        reference = data.get('reference')
        if reference is not None:
            if len(reference) != 2:
                raise ValueError(f"transform.reference は [幅, 高さ]: {reference!r}")
            reference = (int(reference[0]), int(reference[1]))
        interpolation = str(data.get('interpolation', 'linear'))
        if interpolation not in cls.INTERPOLATIONS:
            raise ValueError(
                f"transform.interpolation は {cls.INTERPOLATIONS} のいずれか: {interpolation!r}")
        return cls(
            rotate_deg=float(data.get('rotate_deg', 0.0)),
            quad=quad,
            reference=reference,
            interpolation=interpolation,
        )

    def resolve_quad(self, width: int, height: int) -> List[Tuple[float, float]]:
        """実素材の解像度に対する四隅を返す"""
        if self.quad is None:
            return quad_for_rotation(width, height, self.rotate_deg)

        quad = self.quad
        if self.reference and tuple(self.reference) != (width, height):
            ref_w, ref_h = self.reference
            if ref_w <= 0 or ref_h <= 0:
                raise ValueError(f"transform.reference が不正: {self.reference!r}")
            sx, sy = width / ref_w, height / ref_h
            quad = [(x * sx, y * sy) for x, y in quad]
        return quad

    def filter_str(self, width: int, height: int) -> str:
        """perspective のフィルタ文字列

        sense=source は「ここに挙げた**ソース上の**点を、出力の四隅へ送る」。
        逆（destination）と取り違えると補正が反対にかかる。
        """
        quad = self.resolve_quad(width, height)
        coords = ":".join(
            f"{name}={value:.3f}"
            for name, value in zip(
                ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"),
                [v for pt in quad for v in pt],
            )
        )
        return f"perspective={coords}:interpolation={self.interpolation}:sense=source"
