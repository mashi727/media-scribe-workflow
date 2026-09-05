---
type: worklog-index
---

# Worklog Index

## テーマ
- [av-sync](av-sync/) — 最終 2026-09-06 — 別録りL/R音声と映像の同期ツールチェーン（相互相関・ドリフト補正・全域整合検証・rehearsal-sync）。9/6に記録メディアの埋め込み時刻からの自動同期を実測調査（映像=UTC creation_timeで絶対時刻あり／音声=TC非搭載で絶対時刻ゼロ）、試作2ツール破棄・README刷新
- [transcription](transcription/) — 最終 2026-08-14 — 一次収録から原本の凍結・2エンジン転写（Whisper/Deepgram）・演奏区間検出・リハーサル記録PDFまでの配管。一次資料は words.json + meta.json で SRT は派生

## 2026
- [[2026-05-17]] — リポジトリ3分割合意（CLI/GUI/Report+Archive）、開発ログ42MBをarchive退避、git filter-repoでvideo-chapter-editor抽出（78commits/4.3MB）, Snakemake採用決定とOption B移行設計書525行作成（commit 6ac1e49）
