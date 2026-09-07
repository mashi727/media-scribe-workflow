---
type: worklog-index
---

# Worklog Index

## テーマ
- [av-sync](av-sync/) — 最終 2026-09-07 — 別録りL/R音声と映像の同期ツールチェーン（相互相関・ドリフト補正・全域整合検証・rehearsal-sync）。9/7に TC 同期（`sync.method: tc`）を実装：RODE Wireless Pro の BWF `bext.TimeReference` で構造化＋相関1回でカメラの定常 skew を校正、L↔R は TC 差で確定。依存ゼロの `tc-offset` 新規。実測 skew +129.8s／L↔R 一致 0.2ms／全域 ±0.4ms（`d1ca4e3` 未push）
- [cli-encode](cli-encode/) — 最終 2026-09-07 — エンコードを CLI（vce-encode/vce-split）へ集約し chaptr を章立て作成専用の単一ソース GUI へ。多ソース束ね（.vce.json）退役→章立て .txt 一本化、プロキシ廃止で総エンコ1回。vce-encode に `--source`/`--fhd`/`--youtube-chapters`。`static_ffmpeg`(Rosetta) 長尺失敗の根因特定→システム ffmpeg 優先。chaptr branch `refactor/cli-encode-single-source`（6commit 未merge）、media-scribe `61e91a2`/`5b0b142`（未push）
- [transcription](transcription/) — 最終 2026-09-06 — 一次収録から原本の凍結・多エンジン転写（Whisper/kotoba/Deepgram）・演奏区間検出・リハーサル記録PDFまでの配管。一次資料は words.json + meta.json で SRT は派生。9/6 に 2026-08-23 合同練習で [5]転写〜[8]ダッシュボード公開を初の全通し運用（3PDF全QA合格・events32件・第14回＋定禅寺へ取り込み→Deploy success）

## 2026
- [[2026-05-17]] — リポジトリ3分割合意（CLI/GUI/Report+Archive）、開発ログ42MBをarchive退避、git filter-repoでvideo-chapter-editor抽出（78commits/4.3MB）, Snakemake採用決定とOption B移行設計書525行作成（commit 6ac1e49）
