---
type: worklog-theme-index
theme: av-sync
---

# Worklog — av-sync

別録りL/R音声とカメラ映像の同期ツールチェーン。相互相関による同期・ドリフト補正・
全域整合検証と、YAML駆動オーケストレータ `rehearsal-sync`。

## 2026
- [[2026-07-22]] — 同期ツールチェーン新規構築（audio-sync-offset / audio-sync-verify / audio-drift-correct / audio-merge-stereo / rehearsal-sync）、11コミット。TX1/TX2が独立レコーダーと判明し「各chを映像へ個別同期→結合」へ設計変更。スコア高でも一部一致を見抜けない問題を複数地点検証で解決。実素材5テイク（約16時間・240GB）を処理・検証
