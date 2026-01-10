# VCE 機能マトリクス

実装コードから抽出した全機能一覧。機能図との差分を明示。

## 凡例

- ✅ 機能図に含まれている
- ❌ 機能図に含まれていない（追加が必要）
- ⚠️ 部分的に含まれている

---

## 1. 入力系

| 機能 | 実装クラス/メソッド | 機能図 | 備考 |
|------|-------------------|--------|------|
| YouTube URL入力 | `YouTubeDownloadMixin._start_youtube_download` | ✅ | |
| YouTube再生リスト | `PlaylistInfoWorker`, `PlaylistDownloadWorker` | ✅ | |
| プレイリスト選択UI | `PlaylistVideoSelectionDialog` | ❌ | ダイアログ追加必要 |
| 単一ファイルOpen | `MainWorkspace._open_source_dialog` | ✅ | |
| 複数ファイルOpen | `MainWorkspace._load_multiple_sources` | ✅ | |
| ドラッグ&ドロップ | `DropVideoFrame`, `DragDropTableWidget` | ✅ | |
| フォルダドロップ | `MainWorkspace._on_folder_dropped` | ❌ | |
| ソース追加 | `MainWorkspace._add_sources` | ✅ | |
| ソース削除 | `MainWorkspace._remove_source` | ⚠️ | UI操作にRemove Sourceはあるが詳細なし |

---

## 2. 再生・表示系

| 機能 | 実装クラス/メソッド | 機能図 | 備考 |
|------|-------------------|--------|------|
| 動画プレビュー再生 | `PlaybackManager.toggle_playback` | ✅ | |
| 再生/一時停止 | `PlaybackManager.play`, `.pause` | ✅ | |
| 停止 | `PlaybackManager.stop` | ❌ | |
| シーク | `PlaybackManager.seek_virtual`, `.seek_relative` | ❌ | |
| 波形表示 | `WaveformWidget`, `WaveformWorker` | ✅ | |
| スペクトログラム | `SpectrogramWorker` | ✅ | |
| 仮想タイムライン | `PlaybackManager._virtual_to_source` | ✅ | |
| チャプターマーカー | `WaveformWidget.set_chapters` | ✅ | |
| ファイル番号表示 | `WaveformWidget.set_file_boundaries` | ✅ | |
| 除外区間表示 | `WaveformWidget._get_excluded_regions` | ❌ | |
| チャプターオーバーレイ | `MainWorkspace._update_chapter_overlay` | ❌ | 動画上のタイトル表示 |
| 音声デバイス選択 | `AudioDeviceComboBox`, `MainWorkspace._populate_audio_devices` | ❌ | |
| ソースリスト表示 | `SourceListWidget` | ❌ | 左パネルのソース一覧 |

---

## 3. 編集系

| 機能 | 実装クラス/メソッド | 機能図 | 備考 |
|------|-------------------|--------|------|
| チャプター追加 | `ChapterManager.add_chapter` | ✅ | |
| チャプター編集 | `ChapterManager.update_chapter` | ✅ | |
| チャプター削除 | `ChapterManager.remove_chapter` | ✅ | |
| チャプター移動 | `ChapterManager.move_chapter` | ✅ | |
| 除外区間設定 | `ChapterInfo.is_excluded` | ✅ | |
| チャプター貼り付け | `MainWorkspace.paste_chapters` | ❌ | |
| チャプターファイル読み込み | `ChapterManager.load_from_file` | ❌ | |
| 埋め込みチャプター抽出 | `ChapterManager.extract_from_media` | ❌ | |
| ソース並べ替え | `ReorderSourcesDialog`, `SourceFileManager.reorder_sources` | ⚠️ | ダイアログ追加必要 |
| ソース間移動（行ドラッグ） | `DragDropTableWidget._handle_row_move` | ❌ | |

---

## 4. 出力系

| 機能 | 実装クラス/メソッド | 機能図 | 備考 |
|------|-------------------|--------|------|
| プロジェクト保存 | `MainWorkspace.save_project` | ✅ | |
| プロジェクト読み込み | `MainWorkspace.load_project` | ❌ | |
| チャプター付きMP4 | `ExportWorker`, `vce-encode` | ✅ | |
| 分割動画 | `SplitExportWorker`, `vce-split` | ✅ | |
| 音声のみ抽出 | `ExportWorker._export_audio_with_cover` | ✅ | |
| YouTubeチャプターリスト | `MainWorkspace._copy_youtube_chapters` | ✅ | |
| MovieViewer用チャプター | `ExportWorker._create_chapter_textfiles` | ✅ | |
| チャプターファイル保存 | `ChapterManager.save_to_file` | ❌ | |
| エクスポート設定 | `ExportSettingsDialog` | ❌ | ダイアログ追加必要 |
| バッチエンコード | `BatchEncodeDialog`, `CLIEncodeWorker` | ❌ | |

---

## 5. 設定・管理系

| 機能 | 実装クラス/メソッド | 機能図 | 備考 |
|------|-------------------|--------|------|
| 設定ダイアログ | `PreferencesDialog` | ❌ | |
| テーマ管理 | `ThemeManager` | ❌ | |
| カラースキーム | `Colors`, `ButtonStyles` | ❌ | |
| カバー画像編集 | `CoverImageDialog`, `ImageCropWidget` | ❌ | |
| ログパネル | `LogPanel` | ❌ | |
| アップデート確認 | `UpdateChecker`, `UpdateDownloader` | ❌ | |
| キーボードショートカット | `MainWorkspace.keyPressEvent` | ❌ | |
| 完了フラグ | `MainWorkspace.set_project_complete` | ❌ | |

---

## 6. 内部Manager

| Manager | 実装ファイル | 機能図 | 備考 |
|---------|------------|--------|------|
| PlaybackManager | `managers/playback_manager.py` | ✅ | |
| ChapterManager | `managers/chapter_manager.py` | ✅ | |
| ExportOrchestrator | `managers/export_orchestrator.py` | ✅ | |
| SourceFileManager | `managers/source_manager.py` | ✅ | |

---

## 7. Worker（非同期処理）

| Worker | 用途 | 機能図 | 備考 |
|--------|------|--------|------|
| ExportWorker | エンコード | ⚠️ | 出力で暗黙的に含む |
| SplitExportWorker | チャプター分割 | ⚠️ | 出力で暗黙的に含む |
| WaveformWorker | 波形生成 | ⚠️ | 表示で暗黙的に含む |
| SpectrogramWorker | スペクトログラム生成 | ⚠️ | 表示で暗黙的に含む |
| YouTubeDownloadWorker | YouTube DL | ⚠️ | 入力で暗黙的に含む |
| PlaylistInfoWorker | プレイリスト情報取得 | ❌ | |
| PlaylistDownloadWorker | プレイリスト一括DL | ❌ | |
| DurationDetectWorker | 動画長検出 | ❌ | |
| MergeWorker | 動画/音声結合 | ❌ | 複数ソース時の内部処理 |
| SegmentExtractWorker | セグメント抽出 | ❌ | |
| CLIEncodeWorker | CLIエンコード | ❌ | |

---

## 8. CLI（配管層）

| CLI | 用途 | 機能図 | 備考 |
|-----|------|--------|------|
| vce-encode | プロジェクト→動画 | ✅ | |
| vce-split | プロジェクト→分割動画 | ✅ | |

---

## サマリー

### 機能図に含まれている: 28項目
### 機能図に含まれていない: 24項目
### 部分的に含まれている: 8項目

### 追加が必要な主要カテゴリ

1. **ダイアログ群**
   - PlaylistVideoSelectionDialog（プレイリスト選択）
   - ExportSettingsDialog（エクスポート設定）
   - CoverImageDialog（カバー画像編集）
   - ReorderSourcesDialog（ソース並べ替え）
   - BatchEncodeDialog（バッチエンコード）
   - PreferencesDialog（設定）

2. **再生操作**
   - 停止、シーク、音声デバイス選択

3. **チャプター操作**
   - ファイル読み込み、保存、埋め込み抽出、貼り付け

4. **設定・管理**
   - テーマ、ログ、アップデート、キーボードショートカット

5. **Worker群**
   - 内部処理を担う非同期ワーカーの明示
