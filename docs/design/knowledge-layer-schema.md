# L3 知識層スキーマ（olog ＋ 豊穣 ＋ 層）

media-scribe-workflow の L3（再利用コンテンツ生成層）が吐く知識構造の最小スキーマ。
設計判断の根拠は本文の各節に、来歴は git 履歴に残す。

## 設計原則（3つ）

1. **決定論的 SoT と 相対的解釈層を分離する。**
   一次資料（メディア＋逐語＋来歴）は決定論的・不変。相関・文脈・程度は"その上の層"に置く。
   混ぜない。SoT を相対化すると忠実さが壊れる。

2. **名詞＝型(object)、動詞＝射(morphism)。ドメイン非依存。**
   olog（Spivak & Kent）に準拠。型の意味はその射の束で定まる（Yoneda）＝関係的・差異的。
   意味を型の内部に持たせない。

3. **相関はタグでなく、豊穣な射の "重み"。文脈（差延）は層の "locale"。**
   タグは平坦・二値・単項で相関を表せない。関連度は [0,1] 値の射（enriched over [0,1]、
   Lawvere）で、意味の文脈依存は locale（sheaf の被覆）で表す。同じ対でも locale が違えば
   重みが違う＝貼り合わせの障害が"真の両義性/差延"。

## レコードは4種（JSONL・git-diffable・append 志向）

| kind | 対応 | 決定論？ |
|---|---|---|
| `type` | 名詞（olog の object） | スキーマ（クリスプ） |
| `instance` | 実例＋**一次資料への遡及** | 決定論的 SoT の橋 |
| `edge` | 動詞/射。`mode=aspect`(crisp) / `mode=relation`(graded) | aspect=決定論 / relation=相対 |
| `context` | 文脈＝層の locale（入れ子で抽象度軸） | 座標系 |

### type（名詞・object）
```json
{ "kind": "type",
  "id": "type:instruction",
  "label": "a conductor's instruction",   // 名詞句（olog 規約）
  "profile": "core",                       // core=ドメイン非依存 / orchestral_rehearsal / conference ...
  "def": "指揮者が合奏を止めて与える指示" }
```

### instance（実例・SoT への遡及）＝**決定論的な錨**
```json
{ "kind": "instance",
  "id": "inst:R05",
  "type": "type:instruction",
  "surface": "71小節をスタッカートで前に出す",   // 逐語 or 軽微整形（観測）
  "sot": {                                       // ここが不変の来歴。全ノードが媒体へ遡れる
    "media": "20260802_practice.mp4",
    "t_start": 2827.0, "t_end": 2835.2,
    "segments": ["seg:112", "seg:113"],          // 一次 SoT 転写のセグメントID
    "speaker": "spk:conductor",
    "confidence": 0.86,                           // ASR の語/区間確信度
    "backend": "deepgram-nova3"                   // 転写バックエンドの来歴
  } }
```

### edge（射）— crisp な aspect と graded な relation を mode で分ける
```json
// (a) 決定論的な aspect（olog の骨格。函数的な事実。SoT に錨）
{ "kind": "edge", "id": "e:1", "mode": "aspect",
  "verb": "targets",                             // 動詞句
  "src": "inst:R05", "dst": "inst:passage-m71",
  "sot": { "media": "20260802_practice.mp4", "t_start": 2835.2, "t_end": 2850.0 } }

// (b) 相対的な relation（豊穣な射。相関＝重み。文脈＝差延の locale）
{ "kind": "edge", "id": "e:2", "mode": "relation",
  "verb": "co-emphasized-with",
  "src": "type:articulation", "dst": "type:balance",
  "weight": 0.72,                                // [0,1] の程度（相関）。タグではない
  "context": "ctx:brahms1-mvt1",                 // この重みが成立する locale（別 locale では別の値）
  "method": "cooccurrence",                      // 重みの導出法（解釈の来歴）: cooccurrence|embedding|manual
  "evidence": ["inst:R05", "inst:R13", "inst:R31"] }  // SoT に錨づいた根拠
```

### context（文脈＝層の locale。入れ子＝抽象度軸）
```json
{ "kind": "context",
  "id": "ctx:brahms1-mvt1",
  "label": "ブラームス1番 第1楽章の合奏",
  "cover": { "media": "20260802_practice.mp4", "t_start": 2700.0, "t_end": 3600.0 },
  "parent": "ctx:20260802-practice" }            // 入れ子で多重スケール（縦=抽象度）
```

## なぜこれで要件を満たすか

- **忠実な一次資料**：`instance.sot` / `edge.sot` が全ノード・全 crisp 事実を媒体の時刻＋転写＋話者＋
  確信度＋バックエンドへ遡らせる。逐語は上書きしない（校正は別レコードで注記、原 instance は残す）。
- **決定論の限界を超える**：相関は `relation.weight`（豊穣＝程度）、意味の文脈依存は `context`
  （層の locale）。同じ対でも context 違いで weight が違う＝差延。
- **相関≠タグ**：重みは対的・程度付き・文脈局所。タグは高々 `context` の粗いファセット止まり。
- **解釈も監査可能**：`relation.method` ＋ `evidence` で、graded な層すら SoT へ根拠を辿れる。
- **ドメイン非依存**：`type.profile="core"` が全用途共通。会議/講義/リハーサルは profile が型・射を足すだけ。
  例：会議 `type:decision`/`type:action-item`、講義 `type:concept`/`aspect:defined-by`、
  リハーサル `type:instruction`/`type:passage`。スキーマは同一。

## 可視化・vault への接続

- **可視化（2Dの先）**：node=type/instance、crisp edge=aspect、graded edge=relation（weight→距離/濃度）。
  `context.parent` の入れ子で多重スケール（TDA/Mapper 的に解像度を上下）。relation の重みから
  ノード埋め込みを作れば**トピック中心の相対配置**。SoT は下で不変（ノード→媒体時刻へジャンプ）。
- **既存 vault へ**（新規ストアを作らない）：type/instance→ノート（`sot` リンク付き）、
  edge→型付きリンク（frontmatter/Dataview）、weight→リンクのメタデータ。

## ファイル配置（案）

```
<take>/
  <base>.srt / <base>.words.json / <base>.meta.json   # L1: 決定論的 SoT（不変）
  <base>.knowledge.jsonl                               # L3: 本スキーマ（append 志向・再生成可）
```

L1 は不変、L3 は再計算・再解釈可能（SoT を壊さずいつでも作り直せる）。

## 未決事項

- [ ] speaker（話者）を type として一級にするか、instance の属性に留めるか
- [ ] 校正（観測の訂正）レコードの形（原 surface を残しつつ訂正を注記）
- [ ] relation.weight の導出（cooccurrence / 埋め込み / 手動）の既定パイプライン
- [ ] JSON Schema（機械検証）と最小バリデータ
