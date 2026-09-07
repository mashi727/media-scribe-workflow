---
type: worklog-theme-index
theme: cli-encode
---

# Worklog — cli-encode

エンコードを CLI（`vce-encode`/`vce-split`）へ集約し、chaptr をチャプター作成専用の
単一ソース GUI に絞る再整理。多ソース束ね（`.vce.json`）を退役し章立て `.txt` 一本化、
プロキシ廃止で総エンコードを1回に。

## 2026
- [[2026-09-07]] — エンコードを CLI へ集約・chaptr を単一ソース GUI へ改修。chaptr からエンコード/書き出しサブシステムと複数ソース束ねを一掃（Stage A/B・6commit・branch `refactor/cli-encode-single-source`、未merge）、`.vce.json` 退役→章立て `.txt` 一本化。`vce-encode`/`vce-split` が `.txt` 入力対応＋`--source`/`--fhd`/`--youtube-chapters` で FHD YouTube 書き出し。プロキシ廃止（FHD master 直出し＝総エンコ1回）。`static_ffmpeg`(2022 x86_64/Rosetta) 長尺 VideoToolbox 失敗の根因特定→システム ffmpeg 優先へ修正。media-scribe `61e91a2`/`5b0b142`（未push）
