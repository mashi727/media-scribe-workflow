---
type: worklog-theme-index
theme: av-sync
---

# Worklog — av-sync

別録りL/R音声とカメラ映像の同期ツールチェーン。相互相関による同期・ドリフト補正・
全域整合検証と、YAML駆動オーケストレータ `rehearsal-sync`。

## 2026
- [[2026-09-06]] — 記録メディア埋め込み時刻からの自動同期を実測調査：映像(ACE Pro 2)は `creation_time`=UTCで絶対時刻あり／音声(Wireless Pro)は `bext`・`iXML` 無しでTC非搭載＝絶対時刻ゼロ（exiftoolも[System]時刻のみ）。映像の絶対時刻で自動イベント分割・粗い配置は可、フレーム精度は相関リファイン要。`rehearsal-plan` 構想。試作2ツール(audio/video-timeline-assemble)破棄・README刷新
- [[2026-07-22]] — 同期ツールチェーン新規構築（audio-sync-offset / audio-sync-verify / audio-drift-correct / audio-merge-stereo / rehearsal-sync）、11コミット。TX1/TX2が独立レコーダーと判明し「各chを映像へ個別同期→結合」へ設計変更。スコア高でも一部一致を見抜けない問題を複数地点検証で解決。実素材5テイク（約16時間・240GB）を処理・検証
