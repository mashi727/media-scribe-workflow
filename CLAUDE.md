# CLAUDE.md

## プロジェクト概要

リハーサル動画から字幕（SRT）を取得するシンプルな配管ツール群。
「Gitの陶器と配管」の思想に基づき、単一目的のツールを組み合わせてワークフローを構築する。

## 設計方針

### スコープ

```
[media-scribe-workflow の範囲]

コア: 動画/音声 → SRT取得

参考として提供:
├── プロンプト例（Claude, 汎用LLM向け）
└── 自分の環境構築ガイド（Whisper, LuaTeX等）
```

### 階層

```
[誰でも使える]
└── yt-srt（YouTube字幕取得）

[興味があれば]
└── プロンプト例

[本気でやりたい人向け]
└── 自分の環境構築ガイド
```

## ディレクトリ構成（予定）

```
media-scribe-workflow/
├── README.md
├── CLAUDE.md                # このファイル
│
├── bin/                     # コア（配管ツール）
│   ├── yt-srt               # YouTube → SRT
│   ├── video-trim           # 不要部分削除
│   ├── video-chapters       # チャプター結合
│   ├── vce-encode           # VCEプロジェクト → 動画エンコード
│   ├── vce-split            # VCEプロジェクト → チャプター分割
│   └── spd2png              # SPD→PNG変換（PADtools CLI）
│
├── bin/advanced/            # 拡張ツール（自分用）
│   ├── audio-normalize      # 音量正規化
│   ├── audio-extract-channel # チャンネル抽出
│   └── video-replace-audio  # 音声差し替え
│
├── examples/prompts/        # プロンプト例
│   ├── rehearsal-claude.md  # Claude用
│   └── rehearsal-generic.md # 汎用
│
├── docs/
│   ├── pad/                 # PADtools形式フロー図
│   ├── workflow-diagrams.md # Mermaid形式フロー図
│   ├── workflow-basic.md    # 基本ワークフロー説明
│   └── advanced/            # 自分の環境（晒し）
│       ├── my-setup.md
│       ├── whisper-remote.md
│       ├── luatex-docker.md
│       └── claude-commands.md
│
└── gui/                     # GUI（将来）
```

## ワークフロー

### 基本パターン（汎用）

```
生の長時間動画（例: 13:30-17:00）
    ↓
1. 不要部分の削除（video-trim）
   - 休憩、準備、片付けをカット
    ↓
2. 構造化（movie-viewer）
   - 曲ごとにチャプター付け
    ↓
3. 結合（video-chapters）
   - チャプター付き単一MP4
    ↓
4. 字幕取得（yt-srt）
   - SRTファイル出力
```

### 拡張パターン（複数ソース）

```
入力:
├── Wireless Pro（指揮者近くマイク）→ 文字起こし用
└── iPhone（後方動画）→ 映像用

処理:
├── A. 音声処理: normalize → チャンネル抽出
├── B. 映像処理: trim → チャプター付け
└── C. 合成: 動画 + 指揮者音声

字幕取得:
├── YouTube字幕（yt-srt）
└── Whisper（whisper-remote）← 高精度
```

## 関連ツール（独立リポジトリ）

| ツール | 場所 | 役割 |
|--------|------|------|
| movie-viewer | github.com/mashi727/movie-viewer | チャプター作成・再生 |
| luatex-docker-remote | github.com/mashi727/luatex-docker-remote | リモートLaTeXコンパイル |
| whisper-remote | ~/.config/zsh/functions/ | Whisper文字起こし |
| ytdl-claude | ~/.config/zsh/functions/ | YouTube DL |

## 決定事項

1. **言語**: 既存Zsh関数はそのまま維持、GUIのみPython
2. **配布**: このリポジトリは自己完結（依存は明記）
3. **dotfilesとは独立**: 汎用ツールは別管理
4. **出力形式**: ミニマムはMarkdown、拡張でLaTeX

## 実装済みタスク

- [x] bin/yt-srt の作成（YouTube字幕取得）
- [x] bin/video-trim の作成（動画トリミング）
- [x] bin/video-chapters の作成（チャプター結合・埋め込み）
- [x] bin/vce-encode の作成（VCEプロジェクトエンコード）
- [x] bin/vce-split の作成（VCEプロジェクトチャプター分割）
- [x] bin/spd2png の作成（PADtools CLI PNG変換）
- [x] examples/prompts/ の作成（Claude用・汎用プロンプト）
- [x] README.md の更新（新構成を反映）
- [x] docs/advanced/ の作成（環境構築ガイド）
- [x] docs/pad/*.png の生成（PAD図PNG出力）
- [x] bin/advanced/audio-normalize-{loudnorm,peak} の作成（音量正規化）
- [x] bin/advanced/audio-concat の作成（WAV連結）
- [x] bin/advanced/video-concat の作成（映像ロスレス連結）
- [x] bin/advanced/audio-merge-stereo の作成（mono L/R → ステレオ結合）
- [x] bin/rehearsal-finalize-audio の作成（連結＋loudnorm仕上げ、--stereoでL↔R同期→ステレオ化）
- [x] bin/advanced/audio-sync-offset の作成（相互相関で同期オフセット検出）
- [x] bin/advanced/audio-sync-verify の作成（複数地点で同期の整合を検証）
- [x] bin/advanced/audio-drift-correct の作成（2窓測定→atempoでクロックドリフト補正）
- [x] bin/advanced/video-replace-audio の作成（自動同期して音声差し替え、--driftでドリフト補正）
- [x] bin/rehearsal-sync の作成（take.yaml 1枚で一次ファイル→同期済み映像を全自動生成）
- [x] examples/take.yaml の作成（per-take 設定スキーマ）
- [x] bin/advanced/audio-transcribe の作成（Whisper 系。既定 large-v3、SRT + words.json + meta.json）
- [x] bin/advanced/audio-transcribe-dg の作成（Deepgram Nova-3。同一契約で出力）
- [x] examples/terms-orchestral.txt の作成（両エンジン共通の語彙注入ファイル）
- [x] rehearsal-sync --init（テイクフォルダ走査 → take.yaml 生成。尺から drift を自動判定）
- [x] bin/transcribe-srt の作成（動画/音声→複数エンジン[wp=Zeus/kotoba/dg]で複数SRTをワンコマンド生成。cap-spans→normalize-numbers→compare まで）

## 未実装タスク

- [ ] bin/advanced/audio-extract-channel（チャンネル抽出）
- [ ] bin/advanced/transcript-merge（2エンジンの時刻アライン + confidence 重み付き統合）
- [ ] golden set（代表10分の人手正解）と WER/取りこぼし率の実測

## 文字起こしの一次資料ポリシー

一次資料は **メディア + `.words.json` + `.meta.json`** の3点。`.srt` はそこからの
派生（可読層）であり、原本ではない。理由は SRT が規格として

- 確信度を持てない（誤認識が確定事実の見た目になる）
- 来歴を書く場所がない（コメント構文がない）
- cue 分割・改行が表示上の編集判断で、観測単位へ戻せない
- 話者・同時発話を表現できない

から。校正は派生の解釈層で行い、`.srt` / `.words.json` へ書き戻さない。
両エンジンとも `meta.asr.engine`（`whisper` / `deepgram`）と入力の `sha256` を残す。

## コマンド

```bash
# VCEプロジェクトのエンコード（チャプター付き単一動画）
bin/vce-encode project.vce.json
bin/vce-encode project.vce.json --dry-run       # 計画だけ表示
bin/vce-encode project.vce.json -e libx264 -q 1 # エンコーダと品質指定

# VCEプロジェクトのチャプター分割
bin/vce-split project.vce.json
bin/vce-split project.vce.json --dry-run        # 計画だけ表示
bin/vce-split project.vce.json --audio-only     # MP3で出力
bin/vce-split project.vce.json --overlay-title  # タイトル焼き込み

# mono L/R（チャンネル別 loudnorm 済み）を 1 本のステレオに結合
bin/advanced/audio-merge-stereo L.wav R.wav -o stereo.wav
bin/advanced/audio-merge-stereo L.wav R.wav --swap        # L/R入れ替え

# 別録り音源で映像の音声を差し替え（カメラのスクラッチ音声を鍵に自動同期）
bin/advanced/audio-sync-offset video.mp4 external.wav        # オフセットだけ確認
bin/advanced/video-replace-audio video.mp4 external.wav      # 自動同期して差し替え
bin/advanced/video-replace-audio video.mp4 external.wav --offset 2.5   # 手動指定
bin/advanced/video-replace-audio video.mp4 external.wav --codec pcm -o out.mov  # 無劣化mov
bin/advanced/video-replace-audio video.mp4 external.wav --dry-run      # 計画のみ

# 長時間テイク（数時間）: クロックドリフトを自動補正してから差し替え
bin/advanced/video-replace-audio video.mp4 external.wav --drift        # 冒頭/終端2窓でppm補正
bin/advanced/audio-drift-correct video.mp4 external.wav -o ext_fixed.wav  # 補正のみ（ppm表示）

# 一次ファイル（カメラ映像 + 別録りL/R）から全自動（YAML 1枚）
#   フォルダ例: take/{VID_*.mp4, L/*.wav, R/*.wav} + take.yaml
#   L/R は独立レコーダーのため、各chを映像へ個別同期してから結合する
bin/rehearsal-sync <take_dir> --init    # フォルダを走査して take.yaml を生成（要確認）
#   映像1セッションなら take.yaml を1枚。複数セッション（Insta360 Camera01 の
#   VID_日付_時刻_NNN が複数時刻を持つ等）なら take_<日付_時刻>.yaml を各々吐く。
#   L/R は _TX1_L / _TX2_R のサフィックスで判定、音声は録音時刻(mtime)の空白
#   （無ければ尺構造）でセッション分割し、頭のテスト録りを除いて映像と時系列対応。
bin/rehearsal-sync <take_dir> --init --force  # 既存 take.yaml/take_*.yaml を上書き
bin/rehearsal-sync take.yaml            # 連結→loudnorm→各ch個別同期→結合mux
bin/rehearsal-sync take.yaml --dry-run  # 計画のみ
bin/rehearsal-sync take.yaml --keep-work -v  # 中間生成物を残す/詳細ログ
# スキーマ: examples/take.yaml

# 文字起こし: 動画/音声→複数エンジンで複数SRTをワンコマンド（wp=Zeus/kotoba/dg を束ねる）
bin/transcribe-srt video.mp4                       # 既定 wp,kotoba,dg（dg はキーがあれば自動追加）
bin/transcribe-srt take_L.wav --engines kotoba --terms examples/terms-orchestral.txt
bin/transcribe-srt video.mp4 --dry-run             # 実行せず計画（全コマンド）を提示
#   各SRTに cap-spans→normalize-numbers を掛け、srt-compare で実測サマリまで出す
#   wp は whisper-remote(Zeus)経由で SRT のみ。3層(words/meta)が要るなら下の個別ツールを使う

# 文字起こし（2エンジン並走。出力契約は共通: .srt / .words.json / .meta.json）
#   入力は原盤の WAV/FLAC を使う（非可逆・低ビットレートは警告が出る）
#   語彙ファイルは両エンジンで共用（1行1語・# コメント可）
bin/advanced/audio-transcribe take_L.wav -o take_L_wp --terms examples/terms-orchestral.txt
bin/advanced/audio-transcribe take_L.wav --no-word-timestamps --model kotoba-tech/kotoba-whisper-v2.0-faster  # 速度優先
bin/advanced/audio-transcribe-dg take_L.wav -o take_L_dg --terms examples/terms-orchestral.txt --diarize
bin/advanced/audio-transcribe-dg take_L.wav --dry-run    # 送信せず計画のみ
#   Deepgram は DEEPGRAM_API_KEY（または --key-file）が必要。音声を外部送信する点に注意
#   既存の出力があれば停止する（意図した上書きのみ --force）

# LuaTeXコンパイル
luatex-pdf <file.tex>

# PAD図をPNGに変換（CLI）
bin/spd2png docs/pad/workflow-basic.spd docs/pad/workflow-basic.png 2.0

# 全SPDファイルをPNG化
for spd in docs/pad/*.spd; do bin/spd2png "$spd" "${spd%.spd}.png"; done

# PAD図の編集（GUI）
java -jar $PADTOOLS_HOME/PadTools.jar docs/pad/workflow-basic.spd
```

## 参考

- 収録→ダッシュボードの通し手順（入出力・設計意図の系譜つき）: docs/workflow-rehearsal-to-dashboard.md
- Mermaid形式のワークフロー図: docs/workflow-diagrams.md
- PAD図（ソース）: docs/pad/*.spd
- PAD図（PNG）: docs/pad/*.png
- PADtools: https://github.com/knaou/padtools

## 将来の検討事項 (Action Items)

### mpv統合によるインターレース対応

**背景**: インターレース映像（1080i等）の再生時、QMediaPlayer/AVFoundationの自動デインターレースが不十分で、動きのあるシーンでコーミングが発生する。

**提案**: QMediaPlayerからmpv/libmpvへの移行

**メリット**:
- リアルタイムハードウェアデインターレース（yadif/bwdif）
- 処理オーバーヘッドなし
- クロスプラットフォーム対応（macOS VideoToolbox, Windows DXVA2/D3D11VA, Linux VAAPI）

**実装方針**:
- python-mpvを使用
- PlaybackManagerのインターフェースは維持し、内部実装をmpvに置換
- mpv-2.dll（Windows）/ libmpv.dylib（macOS）の同梱が必要（+約50MB）

**優先度**: 中（インターレース映像の使用頻度による）

**参考検証**: `/Users/mashi/Dropbox/01_Projects/00_SB2009_Affairs/SB2009_10th_Anniversary/Project_D_FinalMix.mov` (1080i, top field first)
