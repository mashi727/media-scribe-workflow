# 開発ログ 2026-01-01

メッセージ数: 6

---

## 👤 User (09:36:10)

このアプリ、iPad用にリリースするとなると大変ですかね。

---

## 🤖 Assistant (09:36:33)

かなり大変です。主な課題:

## 技術的な障壁

| 要素 | 現状 | iPad移植 |
|------|------|----------|
| GUI | PySide6 (Qt) | iOS非対応 |
| 言語 | Python | iOS公式サポートなし |
| 動画処理 | ffmpeg (CLI) | 要ネイティブビルド |
| ファイルアクセス | 自由 | サンドボックス制限 |

## 選択肢

### 1. ネイティブ書き直し (最も現実的)
- Swift + SwiftUI
- AVFoundation (動画処理)
- 工数: 大

### 2. クロスプラットフォーム
- **Flutter** / **React Native** - モバイル向け
- Kotlin Multiplatform
- 工数: 中〜大

### 3. Web + サーバー構成
- フロントエンド: Web (PWA)
- バックエンド: 現在のPython処理をAPI化
- iPad: Safari/WebViewで利用
- 工数: 中

### 4. Catalyst (macアプリ → iPad)
- macOS版を先に作成 → iPad互換
- Qt/PySide6では難しい

## 現実的な結論

**Web版**が最も移植しやすい:
- フロントエンド: React/Vue
- バックエンド: FastAPI + ffmpeg
- iPad: ブラウザで利用

ただし、ローカル処理ではなくサーバー処理になるため、使い勝手は変わります。

本格的にiPad対応するなら、Swiftで書き直すのが最も確実です。

---

## 👤 User (10:13:40)

Tauri版を作成して、Swiftに向かうのはいかがでしょう。

---

## 🤖 Assistant (10:14:07)

良いアプローチです。Tauri 2.0はiOS/Androidサポートがあります。

## 移行パス

```
現在 (PySide6)
    ↓
Tauri 2.0 (Rust + Web)
    ↓
├── デスクトップ: そのまま利用
├── iPad: Tauri iOS (実験的)
└── 必要なら: Swift書き直し (知見を活用)
```

## Tauri版の構成

```
tauri-video-chapter-editor/
├── src-tauri/          # Rust バックエンド
│   ├── src/
│   │   ├── main.rs
│   │   ├── ffmpeg.rs   # ffmpeg操作
│   │   └── chapters.rs # チャプター処理
│   └── Cargo.toml
├── src/                # Web フロントエンド
│   ├── App.tsx         # React/Vue/Svelte
│   ├── components/
│   │   ├── VideoPlayer.tsx
│   │   ├── ChapterTable.tsx
│   │   └── WaveformView.tsx
│   └── styles/
└── tauri.conf.json
```

## メリット

| 項目 | 内容 |
|------|------|
| コード共有 | デスクトップ/モバイルで同一フロントエンド |
| パフォーマンス | Rustバックエンドは高速 |
| バイナリサイズ | Electronより小さい (~10MB) |
| 学習効果 | Rust → Swift移行時に役立つ |

## 課題

| 項目 | 対策 |
|------|------|
| Tauri iOS | まだベータ、制限あり |
| ffmpeg | iOS向けビルドが必要 |
| 動画プレビュー | Web: `<video>`タグ、iOS: ネイティブ連携 |

## 推奨ステップ

1. **Tauri デスクトップ版**を先に作成
2. **iOS版をテスト** (Tauri 2.0 mobile)
3. 問題があれば**Swift版**に切り替え (フロントエンドのロジックは流用可能)

現在のPython実装からRust + Web構成へ移行する価値はあると思います。Tauri iOS がうまく動けばSwift書き直しは不要になる可能性もあります。

---

## 👤 User (10:14:48)

ちょっと考えますね。

---

## 🤖 Assistant (10:14:53)

了解です。検討事項が多いですからね。

今日の成果:
- Split Chapters機能追加
- アップデーター実装
- v2.1.25リリース

何か決まったらお知らせください。

---

