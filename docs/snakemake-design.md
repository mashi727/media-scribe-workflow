# Snakemake 移行設計書

> **配置の暫定性**: このドキュメントは将来 `msw-report` リポジトリに移動する設計資産です。
> リポジトリ分割（CLI / GUI / Report の3分割）が完了するまで、媒体規模上の都合により本リポジトリの `docs/` 配下に置きます。
>
> 関連: `worklog/2026-05-17.md`、本リポジトリの分割計画

---

## 1. 目的

リハーサル/レッスン/会議の動画から、Whisper・YouTube字幕・Claude AI 分析を経由して LuaLaTeX レポート PDF を生成するワークフローを、**既存の `bin/*` スクリプト群を書き換えずに** Snakemake で宣言的に記述する。

### 1.1 解決したい問題

現状のオーケストレーションは以下の問題を抱える:

- **手続き的 zsh スクリプト**（`bin/rehearsal-download`, `bin/rehearsal-finalize`）が暗黙的に DAG を表現しており、依存関係が読みにくい
- **失敗時の再開ポイント**が手動判断（どの SRT が既に存在するかをユーザーが目視）
- **設計だけ存在した独自 YAML ワークフロー**（`examples/transcription_workflow.yaml` schema v1.1）に実装が伴わず、`status.phase` `source.state` の状態追跡が紙の上の設計に留まっている
- **並列化機会の取りこぼし**: 例えば「YouTube DL」と「Whisper への投入準備」は独立だが、現状は直列実行

### 1.2 非目的（やらないこと）

- 既存スクリプト（`bin/yt-srt`, `bin/video-trim`, `bin/msw-pipeline` 等）の書き換え
- `media_scribe_workflow/config/` ConfigLoader の置き換え（VCE 設定マージは現状維持）
- GUI（video-chapter-editor）のオーケストレーション化（GUI は手動操作のまま）
- スケジューラ／常駐サービス化（単発実行のみ）
- 分散実行・クラスタリング（将来オプションとして残すが本設計のスコープ外）

---

## 2. 残す資産・置き換える資産・新規作成

### 2.1 残す（無変更）

| 資産 | 役割 | Snakemake からの参照方法 |
|---|---|---|
| `profiles/orchestral_rehearsal.yaml` | テンプレ定義（field_schema, participants, prompt_template, glossary） | `params:` 経由で YAML 読み込み |
| `profiles/horn_lesson.yaml` | 同上 | 同上 |
| `profiles/meeting_report.yaml` | 同上 | 同上 |
| `media_scribe_workflow/config/` ConfigLoader | VCE 設定の3層マージ | `bin/msw-pipeline` 経由（透過的） |
| `bin/yt-srt` | YouTube DL + 字幕取得 | `shell:` で呼出 |
| `bin/video-trim` | 不要部分カット | `shell:` で呼出（手動判断が要る部分は対話的ルール） |
| `bin/video-chapters` | チャプター結合 | `shell:` で呼出 |
| `bin/vce-encode` / `bin/vce-split` | VCE→動画 | `shell:` で呼出 |
| `bin/msw-config` / `bin/msw-report` / `bin/msw-compile` / `bin/msw-pipeline` | レポート生成 | `shell:` で呼出 |
| `~/.config/msw/{defaults,templates/*}.yaml` | msw 設定階層 | `bin/msw-*` が透過的に読む |

### 2.2 置き換える（捨てる、または再利用）

| 旧資産 | 旧責任 | 新責任 |
|---|---|---|
| `examples/transcription_workflow.yaml` schema v1.1 の `source.state.*` | 4種類の SRT 存在フラグ | **Snakemake のファイル存在判定**で自然に表現 |
| 同 `status.phase` | init→preprocessing→...→done | **DAG の暗黙的トポロジ** |
| 同 `status.artifacts` | 生成済みファイル列挙 | **Snakemake の `--summary`** |
| 同 `status.updated_at` | 最終更新 | **Snakemake のログ** + ファイル mtime |
| `bin/rehearsal-download` 内の暗黙 DAG | YouTube DL → Whisper 投入の手続き的記述 | **rule 間の input/output 連鎖** |
| `bin/rehearsal-finalize` 内の暗黙 DAG | PDF生成 + チャプター抽出 | 同上 |

### 2.3 新規作成

| 新資産 | 役割 |
|---|---|
| `Snakefile` | DAG 本体（ルール集合） |
| `workflow.config.yaml`（プロジェクト固有、作業ディレクトリ配置） | profile 選択・source 情報・fields 値（旧 `transcription_workflow.yaml` の静的部分のみ） |
| `workflows/rules/*.smk` | 機能別ルールセット（ファイルが大きくなったら分割） |
| `workflows/scripts/*.py` | Snakemake から呼ぶ Python ヘルパ（プロファイル展開・プロンプト整形等） |

---

## 3. Snakefile の DAG 構造

### 3.1 ターゲットと中間ファイル

ファイル命名は既存スクリプトの慣習を踏襲する（`*_yt.srt`, `*_wp.srt` など）。

```
[入力]
{name}.url              # YouTube URL を1行記述したテキストファイル（YouTube ソースのみ）
{name}.mp4              # ローカル動画（ローカル ソースのみ）
workflow.config.yaml    # プロジェクト設定

[第1層: ソース取得]
{name}.mp4              # ローカルなら既存、YouTube なら yt-srt が生成
{name}_yt.srt           # YouTube 自動字幕（YouTube ソースのみ）

[第2層: 字幕生成]
{name}_wp.srt           # Whisper 文字起こし結果
{name}_manual.srt       # 手動字幕（存在する場合）
{name}.srt              # 採用された字幕（auto_priority に従いシンボリックリンク or コピー）

[第3層: チャプター編集（GUI 経由、Snakemake はファイル存在を確認のみ）]
{name}.vce.json         # GUI で保存された VCE プロジェクト

[第4層: レポート生成]
{name}.tex              # LuaTeX ソース
{name}.pdf              # 最終 PDF

[第5層: 派生成果物（オプション）]
{name}_split/           # チャプターごとの分割動画ディレクトリ
{name}_encoded.mp4      # チャプター埋め込み済み単一動画
{name}.dag.svg          # ワークフロー可視化
```

### 3.2 ルール定義（Snakefile 雛形）

```python
# ============================================================
# Snakefile — Media Scribe Workflow
# ============================================================
import yaml
from pathlib import Path

configfile: "workflow.config.yaml"

NAME = config["output"]["basename"]
PROFILE_NAME = config["profile"]
SOURCE_TYPE = config["source"]["type"]      # "local" | "youtube"
TRANSCRIPTION_METHOD = config["transcription"]["method"]  # "auto"|"youtube"|"whisper"|"manual"|"skip"
AUTO_PRIORITY = config["transcription"].get("auto_priority", ["whisper", "youtube"])

# プロファイルを読み込み（テンプレ定義はここで展開）
def load_profile(name):
    candidates = [
        Path.cwd() / "profiles" / f"{name}.yaml",
        Path.home() / ".config/rehearsal-workflow/profiles" / f"{name}.yaml",
        Path(workflow.basedir) / "profiles" / f"{name}.yaml",
    ]
    for p in candidates:
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Profile not found: {name}")

PROFILE = load_profile(PROFILE_NAME)

# ============================================================
# 最終ターゲット
# ============================================================
rule all:
    input:
        f"{NAME}.pdf"

# ============================================================
# 第1層: ソース取得
# ============================================================
rule fetch_youtube:
    """YouTube URL から動画 + 自動字幕を取得"""
    input:  "{name}.url"
    output:
        video = "{name}.mp4",
        srt   = "{name}_yt.srt"
    shell:
        """
        url=$(cat {input})
        bin/yt-srt "$url" --video --output-base {wildcards.name}
        """

# ローカルファイルが既に存在する場合、fetch_youtube は走らない（Snakemake が自動判定）

# ============================================================
# 第2層: Whisper 文字起こし
# ============================================================
rule whisper_transcribe:
    """Whisper リモートサーバーで高精度文字起こし"""
    input:  "{name}.mp4"
    output: "{name}_wp.srt"
    threads: 1     # リモート GPU 利用、ローカル CPU は1で十分
    shell:
        """
        whisper-remote --demucs {input} --output {output}
        """

# ============================================================
# 第2.5層: 字幕方式の dispatch
# ============================================================
def select_srt(wildcards):
    """transcription.method と auto_priority に基づき採用する SRT を決定"""
    name = wildcards.name
    if TRANSCRIPTION_METHOD == "youtube":
        return f"{name}_yt.srt"
    elif TRANSCRIPTION_METHOD == "whisper":
        return f"{name}_wp.srt"
    elif TRANSCRIPTION_METHOD == "manual":
        return f"{name}_manual.srt"
    elif TRANSCRIPTION_METHOD == "skip":
        # 既存 .srt を使う（生成しない）
        return f"{name}_existing.srt"
    elif TRANSCRIPTION_METHOD == "auto":
        # auto_priority の最初に存在し得るものを優先
        for method in AUTO_PRIORITY:
            if method == "whisper":
                return f"{name}_wp.srt"   # Snakemake が必要なら whisper_transcribe を起動
            elif method == "youtube":
                return f"{name}_yt.srt"
        raise ValueError(f"auto_priority に有効なエントリなし: {AUTO_PRIORITY}")
    else:
        raise ValueError(f"Unknown transcription.method: {TRANSCRIPTION_METHOD}")

rule select_srt:
    """採用する SRT を {name}.srt にコピー（後段が一意のパスを参照できるようにする）"""
    input:  select_srt
    output: "{name}.srt"
    shell:  "cp {input} {output}"

# ============================================================
# 第3層: VCE プロジェクト（GUI で編集、Snakemake は存在確認のみ）
# ============================================================
# {name}.vce.json は GUI で作成・編集される。Snakemake はファイル存在のみ確認し、
# 無ければエラーで停止する（生成ルールを持たない）。

# ============================================================
# 第4層: レポート生成
# ============================================================
rule generate_report:
    """VCE + SRT → LaTeX → PDF"""
    input:
        vce = "{name}.vce.json",
        srt = "{name}.srt"
    output:
        pdf = "{name}.pdf",
        tex = "{name}.tex"
    params:
        profile = PROFILE_NAME,
        fields  = config["fields"]
    shell:
        """
        bin/msw-pipeline {input.vce} --srt {input.srt} \\
            --output {output.pdf} \\
            --keep-tex
        """

# ============================================================
# 第5層: 派生成果物（オプションターゲット）
# ============================================================
rule encode_video:
    """VCE → チャプター埋め込み単一動画"""
    input:  "{name}.vce.json"
    output: "{name}_encoded.mp4"
    shell:  "bin/vce-encode {input} --output {output}"

rule split_chapters:
    """VCE → チャプター分割動画"""
    input:  "{name}.vce.json"
    output: directory("{name}_split")
    shell:  "bin/vce-split {input} --output-dir {output}"

# ============================================================
# 可視化
# ============================================================
rule dag_svg:
    """ワークフロー DAG を SVG 化"""
    output: "{name}.dag.svg"
    shell:  "snakemake --dag {wildcards.name}.pdf | dot -Tsvg > {output}"
```

### 3.3 DAG 図（概念）

```
                  ┌──────────────┐
                  │  *.url       │ (YouTube 利用時)
                  └──────┬───────┘
                         │
                         ▼ rule fetch_youtube
                  ┌──────────────┐
                  │  *.mp4       │◄──── (ローカル時はファイル直接配置)
                  │  *_yt.srt    │
                  └──────┬───────┘
                         │
                         ▼ rule whisper_transcribe
                  ┌──────────────┐
                  │  *_wp.srt    │
                  └──────┬───────┘
                         │
                         ▼ rule select_srt (method/auto_priority)
                  ┌──────────────┐
                  │  *.srt       │
                  └──────┬───────┘
                         │
              ┌──────────┴──────────┐
              ▼ (GUI 手動)          ▼ rule encode_video / split_chapters
       ┌──────────────┐      ┌──────────────────┐
       │ *.vce.json   │      │ *_encoded.mp4    │
       └──────┬───────┘      │ *_split/         │
              │              └──────────────────┘
              ▼ rule generate_report
       ┌──────────────┐
       │ *.tex *.pdf  │
       └──────────────┘
```

---

## 4. `workflow.config.yaml` 仕様

旧 `examples/transcription_workflow.yaml` の **静的部分のみ** を残し、動的状態（state/status/artifacts/updated_at）は完全に削除する。

```yaml
# workflow.config.yaml schema v2.0 (Snakemake-driven)

schema_version: "2.0"

# プロファイル選択（profiles/{name}.yaml を参照）
profile: "orchestral_rehearsal"

source:
  type: "local"           # local | youtube
  path: "rehearsal_2025-01-03.mp4"

transcription:
  method: "auto"          # auto | youtube | whisper | manual | skip
  language: "ja"
  auto_priority: ["whisper", "youtube"]

fields:
  title: "ブラームス交響曲第1番"
  date: "2025-01-03"
  key_person: "山田太郎"
  organization: "〇〇交響楽団"
  consumer: "団員"

output:
  basename: "rehearsal_record_2025-01-03"
  format: "latex"         # latex | markdown | docx
```

### 4.1 v1.1 からの変更点

| v1.1 のフィールド | v2.0 での扱い | 理由 |
|---|---|---|
| `source.state.*` | **削除** | Snakemake のファイル存在判定 |
| `source.files.*` | **削除** | ファイル名規約から自動導出 |
| `source.working_dir` | **削除** | Snakemake は実行ディレクトリを使う |
| `status.phase` | **削除** | DAG が暗黙的に表現 |
| `status.artifacts` | **削除** | `snakemake --summary` で代替 |
| `status.updated_at` | **削除** | ファイル mtime |

### 4.2 マイグレーション

`bin/migrate-workflow-config` を新規作成し、v1.1 → v2.0 への自動変換を提供。動的セクションは捨て、静的部分だけ抽出する。

---

## 5. プロファイル統合

`profiles/*.yaml` は変更しない。Snakemake からは以下のように利用:

```python
# Snakefile 内
PROFILE = load_profile(PROFILE_NAME)

rule generate_report:
    input: vce="{name}.vce.json", srt="{name}.srt"
    output: pdf="{name}.pdf", tex="{name}.tex"
    params:
        base_template = PROFILE["base_template"],
        macros        = PROFILE["macros"],
        prompt        = PROFILE["prompt_template"],
        glossary      = PROFILE.get("glossary"),
        participants  = PROFILE["participants"],
    shell: "..."
```

`bin/msw-pipeline` 側は profile 名だけ受け取り、内部で同じ load 処理を行う既存実装をそのまま使う。`params:` で渡すのは Snakemake DAG のキャッシュ無効化トリガとしての意味（profile が変われば再実行）。

---

## 6. 想定操作シーン

### 6.1 ゼロから PDF まで一発

```bash
cd ~/Projects/orchestra/2025-01-03/
cat > rehearsal_2025-01-03.url <<< "https://youtu.be/xxxxxxxxxxx"
# workflow.config.yaml を編集（profile, fields 等）
snakemake rehearsal_record_2025-01-03.pdf -j 4
```

`-j 4` で YouTube DL と Whisper を並列実行可能（リソース許す範囲）。

### 6.2 Whisper だけ再実行

```bash
snakemake rehearsal_2025-01-03_wp.srt --forcerun whisper_transcribe
```

### 6.3 PDF 生成だけスキップして TeX まで

```bash
snakemake rehearsal_record_2025-01-03.tex
```

### 6.4 失敗から再開

```bash
snakemake rehearsal_record_2025-01-03.pdf --rerun-incomplete
```

Snakemake が「どこまで完了したか」を mtime とロックファイルで自動判定。

### 6.5 ワークフロー可視化（教材用）

```bash
snakemake --dag rehearsal_record_2025-01-03.pdf | dot -Tsvg > workflow.svg
```

PAD図と並ぶ可視化資産になる。

---

## 7. リモート実行（Whisper サーバー）

Whisper はリモート GPU サーバーで実行するため、`whisper_transcribe` ルールは `shell:` 内で `whisper-remote` を呼ぶ。`whisper-remote` は `~/.config/zsh/functions/` の既存関数で、SSH 経由で処理を投げる。

Snakemake の `--cluster` / `--profile` 機構を使えば、将来「Whisper だけ専用サーバー」「ローカル CPU は ffmpeg のみ」のような実行プロファイル分離も可能。本フェーズでは導入しない。

---

## 8. エラー処理・リトライ

Snakemake 標準機能で十分:

- `--rerun-incomplete`: 中断したジョブのみ再実行
- `--keep-going` (`-k`): あるルールが失敗しても独立ルールは継続
- `restart-times: N` (ルール毎指定): 一時的失敗の自動再試行（例: `whisper_transcribe` のネットワーク失敗）

```python
rule whisper_transcribe:
    input:  "{name}.mp4"
    output: "{name}_wp.srt"
    retries: 2
    shell:  "whisper-remote --demucs {input} --output {output}"
```

---

## 9. ディレクトリ構成（msw-report リポジトリ移行後）

```
msw-report/
├── Snakefile                          # DAG 本体（このドキュメントの §3.2 雛形）
├── workflow.config.template.yaml      # 新規プロジェクト用テンプレ
├── workflows/
│   ├── rules/
│   │   ├── fetch.smk                  # ソース取得ルール群
│   │   ├── transcribe.smk             # 字幕生成・選択
│   │   └── report.smk                 # レポート生成
│   └── scripts/
│       ├── load_profile.py            # プロファイル読み込みヘルパ
│       └── render_prompt.py           # Claude プロンプト整形
├── profiles/                          # 既存（無変更）
│   ├── orchestral_rehearsal.yaml
│   ├── horn_lesson.yaml
│   └── meeting_report.yaml
├── bin/                               # 既存スクリプト（無変更）
│   ├── msw-pipeline
│   ├── msw-report
│   ├── msw-compile
│   ├── msw-config
│   ├── vce-encode
│   ├── vce-split
│   ├── yt-srt
│   ├── video-trim
│   ├── video-chapters
│   ├── rehearsal-download             # 当面残す（Snakemake と並行使用可）
│   ├── rehearsal-finalize             # 当面残す
│   └── migrate-workflow-config        # 新規: v1.1→v2.0 変換
├── media_scribe_workflow/             # 既存パッケージ
│   ├── config/                        # ConfigLoader（無変更）
│   ├── pipeline/                      # report_generator, srt_parser
│   ├── core/                          # VCE データモデル（将来活用）
│   └── utils/                         # ユーティリティ
├── docs/
│   ├── snakemake-design.md            # このドキュメント
│   ├── workflow-comparison.md         # 既存（無変更）
│   └── pad/                           # PAD 図（無変更）
└── tests/
    └── test_snakefile_smoke.py        # 新規: 各ルールの dry-run テスト
```

---

## 10. 段階的導入計画

### Phase 1: 設計書（本ドキュメント） ★ 現在地

### Phase 2: msw-report リポジトリ切り出し
- 本リポジトリ分割計画（worklog/2026-05-17.md 参照）の `D. msw-report 切り出し` を完了
- 本ドキュメントを `msw-report/docs/snakemake-design.md` に移動

### Phase 3: スケルトン Snakefile
- 1プロファイル（`orchestral_rehearsal`）で動作する最小 Snakefile を実装
- YouTube ソース → SRT → PDF の最短パスを検証
- 既存 `rehearsal-download` / `rehearsal-finalize` と並行運用

### Phase 4: フル移行
- 3 プロファイル全てを Snakemake 経由で動作させる
- `workflow.config.yaml` schema v2.0 を確定
- `bin/migrate-workflow-config` を実装
- `bin/rehearsal-download` / `rehearsal-finalize` を deprecated（しばらく残す）

### Phase 5: 教材化
- `snakemake --dag` で生成した DAG 図を Udemy コース教材に組み込み
- 「失敗からの再開」「並列実行」「リモート Whisper」を実演

---

## 11. 未決事項（次セッションで決める）

- **GUI と Snakemake の接続**: video-chapter-editor で `.vce.json` を保存後、自動で Snakemake を起動するか？（CLI 派は手動、GUI 派は自動が好まれる）
- **Whisper の中間ファイル管理**: Whisper サーバー側で生成した SRT のローカル取得方法（既存 `whisper-remote` の挙動依存）
- **Claude API 呼び出しのキャッシュ**: 同一プロンプトで再生成しないようにする（コスト削減）。Snakemake のファイルキャッシュで自然に解決するが、プロンプトテキストをファイル化する命名規約が必要
- **マルチセッション対応**: 同日に複数リハーサルを処理する場合のディレクトリ規約
- **Windows 対応**: Snakemake は WSL 推奨。受講生 Windows ユーザー向けの導入ガイドが別途必要
- **Snakemake バージョン固定**: 教材として安定再現したい → `requirements.txt` か `environment.yaml` で pin

---

## 12. 参考

- Snakemake 公式: https://snakemake.readthedocs.io/
- 既存ワークフロー記述: `examples/transcription_workflow.yaml` (schema v1.1)
- 既存スクリプト一覧: `bin/`
- リポジトリ分割計画: `worklog/2026-05-17.md`
- PAD 図: `docs/pad/*.spd`
