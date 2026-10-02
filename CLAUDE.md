# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際のガイドです。

## プロジェクト概要

CalBar — macOS メニューバーに常駐するカレンダー通知アプリ（v2、SwiftUI ネイティブ）。
予定は EventKit から読み、Google カレンダーは macOS のカレンダーに追加した Google アカウント経由で取得する。
機能・設定・ビルド手順は `README.md` を参照。`.agents/` の文書は v1（Python + Playwright 版）のもの。

## ビルド・確認

```bash
swift run CalBarCoreChecks          # ロジックのチェック
scripts/build-app.sh                # build/CalBar.app を作る
scripts/build-app.sh install        # /Applications に入れて起動
swift build && .build/debug/CalBar --render-previews /tmp/calbar-previews   # 画面を PNG に書き出す
```

- Command Line Tools だけの環境では Swift Testing / XCTest が動かないため、チェックは実行ファイル（`Tests/CalBarCoreTests`）にしている。
- `UNUserNotificationCenter` と EventKit の許可は `.app` バンドルとして起動したときだけ働く。`.build/debug/CalBar` を直接起動して確認できるのは `--render-previews` だけ。
- アドホック署名のため、再ビルドするとカレンダーへのアクセス許可を求め直されることがある。
- UI を変えたら `--render-previews` で書き出した PNG を目で見て確認する。

## アーキテクチャ

- `CalBarCore`: OS に依存しないロジック。予定モデル、会議 URL 抽出、進行中・次の予定・参加対象・空き時間の算出、メニューバー表示文字列。ロジックの追加はまずここに置いてチェックを書く。
- `CalBar`: アプリ本体。
  - `AppModel`（`@MainActor @Observable`）が状態の中心。`EKEventStoreChanged`・スリープ復帰・日付変更・設定変更で `reload()` し、5 秒ごとの `tick()` で現在時刻を進めて自動参加を判定する。
  - `CalendarService` は EventKit の読み込みだけを担当する。
  - `NotificationService` は通知のスケジュールと「参加する」「再通知」アクションを担当する。予定ごとに通知 ID を記録し、再読み込みしても同じ通知を二度出さない。
  - `GlobalHotKey` は Carbon の `RegisterEventHotKey` を使う（アクセシビリティ権限が不要）。

## 重要な設計判断

- 辞退した予定は、進行中・次の予定・空き時間の計算から除外する（表示するかどうかは設定で選べる）。
- 次の予定が 5 分以内に始まる場合は、進行中の会議より次の予定を優先して表示し、参加の対象にする。
- 表示するカレンダーは、無効にしたものの ID を保存する方式にしている。新しく追加したカレンダーは初めから表示される。
- ログは `os.Logger`（subsystem `com.calbar.app`）に出す。ファイルには書かない。

## コーディング規約

- Swift 6 の言語モード（strict concurrency）でビルドする。
- UI テキストは日本語でソースに直接書く（i18n 非対応）。
- このリポジトリは公開されている。サンプルデータやテストに、実在の会議 URL・社内の会議名・メールアドレスを入れない。
