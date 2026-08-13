---
type: worklog-theme-index
theme: transcription
---

# Worklog — transcription

一次収録から「原本の凍結 → 2エンジン転写 → リハーサル記録PDF」までの配管。
Whisper（ローカル / Zeus GPU）と Deepgram Nova-3 の併用、演奏区間の検出、
章立てに追随した無劣化カット。

一次資料の定義は **メディア + `.words.json` + `.meta.json`**。`.srt` はそこからの
派生（可読層）であり原本ではない。校正・正規化は必ず派生層で行う。

## 2026
- [[2026-08-13]] — 実素材（レオケ合同練習 4.39h）で全工程を通した。新規7本・改修2本を6コミット。原本＝編集後と決めたことで SRT 再タイミングが不要に。distil+hotwords で出力が空になる罠、長尺VADのcue終端引き伸ばし、whisper-remote の orchestra プリセットのループ暴走を実測で潰した。L↔R が 29ms ずれていたのを聴取で発見（符号を逆に読んで32GB無駄書きも）
