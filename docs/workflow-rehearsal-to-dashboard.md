# 収録からダッシュボードまで — リハーサル記録ワークフロー

カメラ映像と別録り L/R 音声（32-bit float）から、団員ダッシュボードの
一次資料になるまでの全手順。

数値はすべて 2026-08-09 レオケ合同練習（3時間42分・映像9本 33GB・L/R 各5本）の
実測値。所要時間は機材（Apple Silicon Mac ＋ 転写は Zeus GPU）に依存する。

---

## 全体像

```
[0] 収録            カメラ映像 + L/R 別レコーダー（32-bit float）
        ↓
[1] 同期・差し替え   rehearsal-sync            → 全長マスター（4:23:17 / 32GB）
        ↓
[2] 章立ての確定     Chaptr（人）              ← ここが凍結点
        ↓
[3] 原本の凍結       video-cut-chapters        → 原本（3:42:02 / 27GB）
        ↓
[4] 配信用と公開     ffmpeg + YouTube          → videoID
        ↓
[5] 転写            audio-transcribe(-dg)     → .srt / .words.json / .meta.json
        ↓
[6] 記録の作成       /rehearsal skill          → Phase 1/2/3 の .tex → PDF
        ↓
[7] 導線を張る       tex-link-timestamps       → タイムスタンプが YouTube リンクに
        ↓
[8] 取り込み         build_leok_all.py → push  → https://differance-lab.tokyo/leok/
```

**[2] より前は何度でもやり直せる。[3] 以降は章立てに依存するので、切り直すと下流が全部作り直しになる。**
Chaptr での確認を明示的な凍結点として扱うこと。

---

## [0] 収録

| | 構成 |
|---|---|
| 映像 | カメラ（自動分割セグメントは可。**間を空けて撮った別クリップは不可**） |
| 音声 | L/R 別レコーダー・**32-bit float**・指揮台の下に約15cm間隔 |

32-bit float の意味は **クリップしない**こと。ゲインを攻めて設定する必要がなく、
突発的な強奏で潰れない。代わりにファイルが大きい（48kHz なら 4h で約 2.6GB/ch）。

**L/R は独立レコーダーなので、開始時刻もクロックも別。** 15cm 間隔は空間表現ではなく
冗長性（片方のドロップアウト対策）が目的。したがって

- 文字起こしには**片チャンネル単独**を使う。ステレオのまま ASR に渡すと内部のモノラル化で
  L+R が加算され、同期残差ぶんのコムフィルタが生じる（残差 4ms なら 130Hz 以降にノッチが並ぶ）
- L↔R の相対ずれは**人間の耳が 1〜2ms で音像の偏りとして知覚する**。映像基準の許容値
  （0.5秒）を流用してはいけない

フォルダはこの形にしておくと `--init` が走査できる。

```
20260809_レオケ合同練習/
├── insta360/VID_*.mp4     # または直下に VID_*.mp4
├── L/*.wav
└── R/*.wav
```

---

## [1] 同期・差し替え — `rehearsal-sync`

```bash
bin/rehearsal-sync <take_dir> --init      # フォルダを走査して take.yaml を生成
```

生成された `take.yaml` を**必ず目視で確認する**。とくに次の2つ。

```yaml
normalize:
  method: loudnorm        # EBU R128。指示が聞こえることを優先する
  bit_depth: "32f"        # ★ 32f 収録なら 32f のまま通す（既定は "24"）
drift:
  enabled: true           # ★ 1時間超は有効化。機材実測で 9〜17ppm
  window: 120             # 長尺は広げると測定の lever が伸びて精度が上がる
```

`bit_depth` の既定は `"24"`。32-bit float で録ったなら、正規化の途中でクリップさせない
ために `"32f"` を指定する。最終 mux は codec 側で決まる（`aac`→mp4／`pcm`→24bit mov）。

`drift` は映像と音声のサンプルクロック差の補正。15ppm × 3h ≈ 0.16秒 なので、
長尺では末尾で無視できない。迷えば有効にしてよい（|ppm| が小さければ自動で素通しになる）。

```bash
bin/rehearsal-sync take.yaml --dry-run    # 実行される配管コマンドを確認
bin/rehearsal-sync take.yaml              # 本実行
```

処理の流れは **各chを連結 → loudnorm → 映像へ個別同期 → ドリフト補正 → ステレオ結合 → mux**。
L/R を独立に映像へ合わせるので、左右の開始時刻の違いと相互ドリフトが同時に吸収される。

### 検証（自動で走るもの）

| 検証 | 既定 | 意味 |
|---|---|---|
| `sync.min_score` | 10 | 全体相関の信頼度（z値）。共通の音が無い素材を弾く |
| `sync.verify` | true | 複数地点で全域の整合を確認（「一部だけ一致」を見抜く） |
| `sync.channel_tolerance` | 5 ms | **L↔R の相対ずれ**。映像基準とは別に持つ |

`channel_tolerance` は L↔R が 29ms ずれていた事故のあとに追加した。
**各chの対映像残差が小さくても、L↔R がずれることはある。**

出力は**全長マスター**（開始前・休憩・終了後を含む）。実測 4:23:17 / 32GB。

---

## [2] 章立ての確定（人の作業）

**ここが凍結点。** 曲の切れ目と、原本から外す区間（開始前・休憩・終了後）を確定させる。

### 下書きを機械で作る（任意）

```bash
python3 bin/advanced/audio-features <master.mp4> -o feat.npz --report \
    --probe "0:15:00-0:18:00:MUSIC" --probe "0:02:00-0:08:00:SPEECH"
python3 bin/advanced/segments-detect --feat feat.npz \
    --sub *_dg.srt --sub *_wp.srt --chapters chapters_draft.txt -o segments.json
```

`audio-features` は 4.4h を 4.6秒 で処理する。`--report` の分位点と probe を見てから
閾値を決めること（既定は Otsu で自動決定するが、会場が変われば分離点は動く）。

**この下書きは骨格であって結論ではない。** 人が確定させた章立てとの一致率は **52.4%**。
誤りは2型ある。

- **休憩中のざわめきを演奏と誤検出**（実測2区間・33.5分）。高音圧・広帯域・ASR無出力で、
  音響特徴だけでは演奏と区別できない
- **演奏に重ねた指示でトークに倒れる**（実測約60分）

### Chaptr で確定させる

書式は `HH:MM:SS 名称`。原本から外す区間は名前の先頭に `--` を付ける。

```
00:00:00 -- 開始前
00:10:12 練習開始
00:14:09 001 Opening Tune
01:13:40 -- 休憩
...
```

---

## [3] 原本の凍結 — `video-cut-chapters`

```bash
python3 bin/advanced/video-cut-chapters <master.mp4> -c <chapters.txt> --dry-run
python3 bin/advanced/video-cut-chapters <master.mp4> -c <chapters.txt> -o 原本.mp4
```

`--` 付き区間を除いて concat demuxer の inpoint/outpoint で**無劣化カット**する
（キーフレームにスナップ）。実測 41.3分を除いて 43秒で完了、3:42:02 / 27GB。

同時に**チャプターを再計時**して 2 つ書き出す。

- `原本.txt` — 新しいタイムラインの章立て（以降すべての基準）
- `原本_youtube.txt` — YouTube 説明欄に貼る形式

> **原本＝全記録から開始前・休憩・終了後を除いたもの。** カメラをいつ回し始めたかは
> 合奏の性質ではないので、記録の境界は出来事の側で定義する（アーカイブ学の appraisal）。
> この前提を採ると転写を編集の後ろに置けるので、**SRT の再タイミングが不要になる**。

---

## [4] 配信用エンコードと公開

```bash
ffmpeg -i 原本.mp4 -c:v libx265 -crf 24 -tag:v hvc1 -c:a aac -b:a 192k 原本_YouTube.mp4
```

実測 4.8GB / 3.10Mbps・SSIM 0.986。VideoToolbox（ハードウェア）は速いが効率が劣り、
同じ SSIM に 6.4Mbps を要した。**急がないなら libx265。**

YouTube にアップロードし、`原本_youtube.txt` を説明欄へ貼る。**videoID を控える**
（`https://youtu.be/25MxIZQ8JLU` の `25MxIZQ8JLU`）。以降 2 箇所で使う。

> 手元に動画を残さない運用も成立する。**Chaptr のチャプター付けが不変である限り**、
> YouTube から取り直した音声で転写しても実質的な差は出ない（原盤 29401字 対
> YouTube経由 28958字、差 1.5%）。

---

## [5] 転写 — 2エンジン並走

**入力は片チャンネルの WAV。**（[0] の理由による。ステレオを渡さない）

```bash
# Whisper large-v3（Zeus GPU 664秒 / 3.7h）
bin/advanced/audio-transcribe take_L.wav -o take_L_wp \
    --terms examples/terms-orchestral.txt --no-condition --chunk 10

# Deepgram Nova-3（約3分 / 3.7h。音声が外部へ出る点に注意）
bin/advanced/audio-transcribe-dg take_L.wav -o take_L_dg \
    --terms examples/terms-orchestral.txt
```

出力は両エンジン共通で **`.srt` / `.words.json` / `.meta.json`** の3点。

### 必ず付けるオプションと理由

| オプション | 理由 |
|---|---|
| `--no-condition`（Whisper） | `condition_on_previous_text` を切る。**入れないと同一文が 4348回**出る（実測）。処理時間も 4410秒→664秒 |
| `--chunk 10`（Whisper） | 長尺 VAD による cue 終端の引き伸ばしを chunk 長で頭打ちにする |
| `--terms`（両方） | 語彙注入。ファイルは両エンジンで共用。Deepgram は 500トークン上限があり、**日本語は1文字≒1トークン**なので送信前に自動で切り詰める |

**distil 系モデルに `--terms` を渡してはいけない。** デコーダ2層でプロンプトを扱えず、
**出力が丸ごと空になる**（exit code 0・`.words.json` は出るので成功に見える）。
現在は自動で無効化して警告する。

### 派生層の整形

```bash
python3 bin/advanced/srt-cap-spans     take_L_wp.srt --stats     # まず統計だけ見る
python3 bin/advanced/srt-cap-spans     take_L_wp.srt -o take_L_wp.capped.srt
python3 bin/advanced/srt-normalize-numbers take_L_dg.srt --keep 第九 -o take_L_dg.num.srt
```

`srt-cap-spans` は同じファイルから発話速度を実測して cue の終端を抑える
（実測 4.5〜8.6 文字/秒、エンジンと素材による）。**cue の開始は信頼できる。壊れるのは終端だけ。**

`srt-normalize-numbers` は漢数字→算用数字。Deepgram の `numerals` は日本語で効かないため
（2素材で再現）。`--keep` で固有名詞を守る。

> **一次資料は メディア + `.words.json` + `.meta.json`。`.srt` は派生（可読層）。**
> SRT は確信度を持てず、来歴を書く場所がなく、cue 分割が表示上の編集判断で観測単位へ戻せず、
> 話者・同時発話を表現できない。校正は解釈層で行い、`.srt` / `.words.json` へ書き戻さない。

### エンジンの序列（実測・実質情報量で評価）

| 系統 | 全文字 | 幻聴 | 幻聴率 | 実質 |
|---|---|---|---|---|
| **Deepgram nova-3** | 23572 | 75 | **0.3%** | **23497** |
| Clipto | 28958 | 6175 | 21.3% | 22783 |
| Whisper（VADなし） | 22322 | 3294 | 14.8% | 19028 |
| Deepgram nova-2 | 22663 | 1373 | 6.1% | 21290 |

**文字数で評価すると結論が正反対になる。** 「ご視聴ありがとうございました」等の
YouTube字幕由来の学習痕跡を数えないこと。

---

## [6] 記録の作成 — `/rehearsal` skill

```
/rehearsal <作業ディレクトリ>
```

Phase 0（素材の棚卸し）→ 前提条件の確認 → Phase 1/2/3 と進む。詳細は
`~/.claude/skills/rehearsal/SKILL.md`。

| 段階 | 成果物 | 何を答えるか |
|---|---|---|
| Phase 1 | `..._リハーサル記録.pdf` | 何が起きたか |
| Phase 2 | `..._合奏返し全記録.pdf` | なぜそこを止め、返したか |
| Phase 3 | `..._統合記録.pdf` | 一次資料（1と2を1本化） |

**ダッシュボードが読むのは統合記録の `.tex` だけ。** Phase 1・2 は統合記録の材料であり、
配布物としても意味があるが、取り込みには使わない。

品質ゲート（全部通すこと）:

```bash
python3 ~/.claude/skills/rehearsal/scripts/layout_qa.py <出力>.pdf
```

章立てはチャプターに一致させる。同じ曲が複数チャプターに分かれていても**統合しない**
（1度失敗している）。

---

## [7] タイムスタンプを YouTube リンクにする

```bash
python3 bin/advanced/tex-link-timestamps <統合記録.tex> --video 25MxIZQ8JLU --in-place
```

**本文の `\ts{HH:MM:SS}` は 1 文字も変更されない。** プリアンブルの `\ts` の定義だけが
リンク版に差し替わり、時刻→秒の対応表が添えられる。巻き戻しは `--unlink`。

> **なぜ呼び出し側を変えないか。** この `.tex` は PDF 化のほかに
> `build_leok.py` からも解析される。同スクリプトは `\ts{}` を特別扱いして
> `<span class="leok-ts" data-sec="...">` を出し、それがページ内 YouTube 再生の
> フックになっている。呼び出し側を書き換えると **`data-sec` が消えて再生が死に、
> 秒数が本文へ漏れる**。実測:
>
> ```
> \ts{00:47:07}         -> <span class="leok-ts" data-sec="2827">[00:47:07]</span>
> \tsy{00:47:07}{2827}  -> 00:47:0771小節 2827 を返す
> ```
>
> `build_leok.py` は `\begin{document}` 以降しか読まないので、**プリアンブルの変更は
> 下流から不可視**。この性質を使って界面を固定している。

掛けたあと再コンパイルし、リンク数を検算する。

```bash
luatex-pdf <統合記録.tex>
python3 ~/.claude/skills/rehearsal/scripts/layout_qa.py <統合記録.pdf>
```

---

## [8] ダッシュボードへ取り込む

作業は `differance-lab` リポジトリ（`git@github.com:mashi727/differance-lab.git`）。

### 8-1. 素材を置く

```
resources/情報まとめ/<公演>/           ← gitignore 配下。ローカルのみ
    20260809_合同練習_統合記録.tex
    20260809_合同練習_統合記録.pdf
```

ファイル名から日付（`YYYYMMDD`）と種別が判定される。トップレベルの `*.tex` だけが拾われる。

### 8-2. 動画IDを登録する

`scripts/leok_videos.json` に `練習日 → videoID` を足す。

```json
"videos": { "2026-08-09": "25MxIZQ8JLU", ... }
```

同日に午前/午後の2本があるときは `{"am": "...", "pm": "..."}`。ファイル名の
「午前」「午後」で振り分けられる。

### 8-3. ビルドして確認

```bash
python3 scripts/build_leok_all.py
```

`assets/leok-private/<id>/` に `manifest.json` / `docs/*.json` / `files/` が生成される。
**`\ts` の呼び出し数と `data-sec` の数が一致することを確認する**（不一致なら [7] が壊れている）。

```bash
python3 -c '
import re, pathlib
raw = pathlib.Path("wp-content/themes/dlab/assets/leok-private/14/docs/2026-08-09-....json").read_text()
print(raw.count("leok-ts"), len(re.findall(r"data-sec=\\\\\"(\d+)\\\\\"", raw)))'
```

### 8-4. コミットして push（＝デプロイ）

```bash
git add scripts/ wp-content/themes/dlab/assets/leok-private/
git commit
git fetch origin && git rebase origin/main    # missponne の自動コミットが先行しがち
git push origin main                          # → Deploy Theme to CoreServer が走る
gh run list --workflow=deploy-theme.yml --limit 1
```

ブラウザキャッシュが残っていると「準備中」のまま見えることがある。ハード再読込で確認。

---

## 1回の練習が複数の公演にまたがる場合

12月本番の曲と定禅寺（9月）の曲を同じ日に扱う、というケース。

**記録は分割しない。** 記録は出来事の単位、曲一覧は演目の単位、と層を分ける。
1回の合奏の記録を2本に割ると、返し番号・章立て・QA が二重になる。

1. 同じ `.tex` を両方の `resources/情報まとめ/<公演>/` に置く
2. 公演ごとに `leok_program.json`（セットリスト）を用意する
3. `build_leok_all.py` の `EDITIONS` にエディションを足し、**セットリストが確定している側だけ**
   `"pieces_in_program": True` にする

```python
{"id": "jozenji26", "label": "定禅寺ジャズフェスティバル", "subtitle": "2026 仙台",
 "date": "2026-09-13", "venue": "仙台・定禅寺通り", "active": False,
 "src": "定禅寺", "use_common": False, "pieces_in_program": True,
 "summaries": RES / "定禅寺" / "leok_summaries.json",
 "program":   RES / "定禅寺" / "leok_program.json"},
```

**プログラムがたたき台の公演には絞り込みをかけない。** かけると、リハで扱ったのに
セットリスト未掲載の曲まで黙って消える。除外された曲はビルド時にログへ出る。

`active` は「**既定で表示する公演**」であって「終了したか」ではない。アーカイブ判定は
公演日で行う（`dlab_leok_edition_is_active()`）。開催予定の公演が複数あるとき、
既定になれるのは1つだけなので兼用すると破綻する。

---

## 所要時間の目安（3時間42分の素材）

| 段階 | 実測 |
|---|---|
| [1] 同期・差し替え | 数時間（I/O 律速。32GB を書く） |
| [2] 章立ての確定 | 人の作業。数時間 |
| [3] 原本の凍結 | **43秒**（無劣化カット） |
| [4] 配信用エンコード | 100分（libx265 crf24） |
| [5] 転写 | Deepgram 3分／Whisper 664秒（Zeus GPU） |
| [6] 記録の作成 | 人＋LLM。数時間 |
| [7] リンク化 | 数秒＋再コンパイル |
| [8] 取り込み・デプロイ | 数分 |

ディスクは**素材の3〜4倍**を見ておく。中間生成物（`.work`）は完了時に自動削除されるが、
`--keep-work` を付けたときは手動で消すこと（実測 46GB）。

---

## 落とし穴（すべて実際に踏んだもの）

| 症状 | 原因 | 対処 |
|---|---|---|
| 左右の音像が偏る | L↔R の相対ずれ（実測 12〜29ms・1.5ppm で増加）。映像基準の許容値は通ってしまう | `sync.channel_tolerance`（5ms）で検出 |
| 補正したら悪化した | 相互相関の符号を逆に読んだ（24.6ms→52.3ms・32GB を無駄に書いた） | 推論に頼らず、既知量を人工的に遅らせて符号を確認してから適用 |
| 転写が空・SRT 0バイト | distil モデル + hotwords。**exit code 0 で `.words.json` は出る** | 自動無効化。`--dry-run` で警告を確認 |
| 同一文が数千回 | `condition_on_previous_text` | `--no-condition` |
| cue の終端が数百秒 | 長尺 VAD。Silero が音楽を発話と判定して切り詰めが効かない | `--chunk 10` ＋ `srt-cap-spans` |
| 漢数字のまま | Deepgram の `numerals` が日本語で効かない | `srt-normalize-numbers` |
| FLAC が元の4.5倍 | 非可逆音源を可逆変換していた | codec 判定で passthrough（修正済み） |
| ダッシュボードで時刻が飛ばない | `.tex` の記法を変えて `data-sec` が消えた | [7] の注記。**成果物の記法を変える前に、他に誰が解析しているか確かめる** |
| 未開催の公演に「アーカイブ」 | `active` を「既定表示」と「終了したか」に兼用 | 公演日で判定 |
| コマンドが黙って走らない | zsh の `nomatch`。先頭の glob 失敗で連鎖ごと中断 | glob を含む連結コマンドに注意 |

---

## 関連

- ツールの一覧と個別の使い方: `CLAUDE.md`
- 記録作成の詳細仕様: `~/.claude/skills/rehearsal/SKILL.md`
- ダッシュボードの構成: `differance-lab/LEOK_DASHBOARD.md`
- 作業ログ: `worklog/transcription/`（ツール側）／
  `differance-lab/worklog/leok/`（取り込み側）
