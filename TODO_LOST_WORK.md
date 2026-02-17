# 失われた作業 (v2.1.34以降)

## 未解決のバグ

- [ ] **ビデオ再生遅延問題**: チャプタークリックでシーク時、音声は即座に再生されるが映像フレーム更新が遅延する
  - 原因候補: PlaybackManagerとMainWorkspaceの両方が`mediaStatusChanged`シグナルに接続し、二重で`play()`を呼んでいた
  - 試した修正（全て効果なし）:
    - `is_playing`チェックを追加
    - QVideoWidgetに`update()`/`repaint()`呼び出し
    - PlaybackManagerの`mediaStatusChanged`接続を削除
    - `_handling_media_status`フラグ追加
    - `QTimer.singleShot`使用
  - **注意**: 1fpsファイル（MP3+静止画）では問題が顕著に見える（これはファイル特性）
  - 通常のフレームレート動画での再検証が必要

---

## CLIツール（bin/）

- [ ] `msw-config` - 設定階層のマージ・検証
- [ ] `msw-report` - .vce.json + SRT → .tex レポート生成
- [ ] `msw-compile` - LaTeXコンパイル（luatex-pdfラッパー）
- [ ] `msw-pipeline` - 全工程の統合パイプライン

## パッケージ構造

- [ ] `media_scribe_workflow/config/` - 設定読み込み・マージ
  - loader.py
  - encoder_config.py
  - encoders.yaml
- [ ] `media_scribe_workflow/pipeline/` - パイプライン処理
  - srt_parser.py
  - report_generator.py
- [ ] `media_scribe_workflow/utils/` - ユーティリティ
  - compat.py（プラットフォーム判定、フォント検出、パスエスケープ）
- [ ] `media_scribe_workflow/ui/controllers/` - UIコントローラー
  - chapter_table_controller.py
  - playback_controller_ui.py
  - source_file_ui.py
  - waveform_manager.py
  - export_manager_ui.py
- [ ] `media_scribe_workflow/ui/dialogs/` - ダイアログ分割
  - source_selection.py
  - export_settings.py
  - その他
- [ ] `media_scribe_workflow/ui/workers/` - Worker分割
  - base.py
  - export.py
  - youtube.py
  - media_analysis.py

## リファクタリング（コード変更）

- [ ] Phase 3.8.1: ChapterManager活性化
  - ChapterManagerのSignalをUIに接続
  - `_add_chapter()` をChapterManager経由に変更
  - `_remove_chapter()` をChapterManager経由に変更
- [ ] Phase 3.8.2: ProjectState Facade化
  - ProjectState.sourcesをプロパティに変更
  - ProjectState.chaptersをプロパティに変更
  - dataclass → 通常クラスに変換
- [ ] Phase 3.8.3: 同期ポイント削除
  - `_sync_source_manager()` 呼び出しを削除
- [ ] Phase 5: クロスプラットフォーム対応
  - プラットフォーム判定統一
  - エンコーダ設定最適化（quality_index対応）
  - フォント検出改善
  - ツールパス解決改善
  - パス処理の抽象化

## テスト

- [ ] tests/test_chapter_manager.py
- [ ] tests/test_export_orchestrator.py
- [ ] tests/test_source_file_manager.py
- [ ] tests/test_utils_compat.py
- [ ] tests/test_log_panel.py
- [ ] その他多数

## ドキュメント

- [ ] docs/DESIGN_PRINCIPLES.md
- [ ] docs/msw_integrated_architecture.md
- [ ] docs/vce-json-spec.md
- [ ] docs/vce_architecture.md
- [ ] docs/vce_feature_matrix.md

---

**注意**: これらは全て git clean で削除されました。
再実装する場合は慎重に進めてください。

---

## コミット済みだが巻き戻された変更 (646d132..97d652e)

以下はv2.1.34に含まれていたが、646d132への巻き戻しで失われた変更:

### bin/vce-split (08996c9)
- チャプターベースの動画分割CLI
- `--audio-only`: MP3出力
- `--overlay-title`: タイトル焼き込み

### SourceFileManager強化 (8bc359d)
- `media_scribe_workflow/ui/managers/source_manager.py` の改善
- PAD図とMermaid図の追加

### GitHub Actions修正
- macOS-13 → macOS-15 更新
- Windows Nuitkaビルド対応
- yt-dlp外部化
- DMG作成のResource busyエラー修正

### YouTubeダウンロードcookies対応 (b32c080)
- `media_scribe_workflow/ui/workers.py` のcross-platform cookies対応

---

## 復旧方法

```bash
# v2.1.34の特定ファイルを復元
git checkout v2.1.34 -- bin/vce-split
git checkout v2.1.34 -- media_scribe_workflow/ui/managers/source_manager.py
git checkout v2.1.34 -- media_scribe_workflow/ui/workers.py
git checkout v2.1.34 -- .github/workflows/release.yml
```
