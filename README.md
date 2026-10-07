# CalBar - macOS メニューバー カレンダー通知アプリ

macOS のメニューバーに常駐して次の予定と残り時間を表示し、開始前に通知するアプリです。
v2 では SwiftUI のネイティブアプリとして作り直し、予定は macOS のカレンダーデータベース（EventKit）から読みます。
Google カレンダーは、macOS のカレンダーに Google アカウントを追加すれば表示されます。

## 機能

- **メニューバー表示**: 次の予定のタイトルと「15分後」、会議中は「残り12分」を表示します。次の予定が 5 分以内に迫ると、終わりかけの会議より次の予定を優先して表示します。
- **予定パネル**: メニューバーをクリックすると、進行中・次の予定のカード（進捗バーと参加ボタン付き）と、その日のタイムラインを表示します。
- **タイムライン**: カレンダーの色、場所、出欠（仮・未回答・辞退）、15 分以上の空き時間、現在時刻の線を表示します。終わった予定は薄く表示します。
- **日付の移動**: 前の日・今日・次の日に切り替えられます。今日の予定が終わった後は、明日の最初の予定を表示します。
- **会議への参加**: Google Meet / Zoom / Teams / Webex の URL を予定の URL 欄・場所・メモから見つけて、「参加」ボタンを出します。
- **ショートカット ⌃⌥J**: どのアプリを使っていても、進行中または 5 分以内に始まる会議に参加できます。
- **通知**: 開始の N 分前に macOS の通知を出します。通知には「参加する」「開始1分前に再通知」のボタンが付きます。
- **自動参加（任意）**: 開始時刻に会議 URL を自動で開きます。
- **リアルタイム反映**: カレンダーが変わると、ポーリングを待たずにすぐ反映します。
- **設定画面**: 通知タイミング、メニューバーの表示形式、表示するカレンダー、ログイン時の起動などを変更できます。

## 必要環境

- macOS 15 (Sequoia) 以降
- Swift 6 ツールチェーン（Xcode または Command Line Tools）
- macOS のカレンダーに追加した Google アカウント（システム設定 > インターネットアカウント）

## ビルドとインストール

```bash
scripts/build-app.sh install
```

`build/CalBar.app` をビルドして `/Applications/CalBar.app` を置き換え、起動します。
旧 Python 版も同じバンドル ID（`com.calbar.app`）なので、起動中なら終了させてから置き換えます。
ビルドだけ行う場合は `scripts/build-app.sh` を引数なしで実行してください。

初回起動時に、カレンダーと通知へのアクセス許可を求められます。どちらも許可してください。
アプリはアドホック署名なので、再ビルドすると macOS が別のアプリとみなし、もう一度許可を求めることがあります。

## 開発

```bash
# ロジック（CalBarCore）のチェックを実行
swift run CalBarCoreChecks

# 画面をサンプルデータで PNG に書き出す（デバッグビルドのみ）
swift build && .build/debug/CalBar --render-previews /tmp/calbar-previews

# 動作ログを見る
/usr/bin/log stream --predicate 'subsystem == "com.calbar.app"' --info
```

Command Line Tools だけの環境では Swift Testing と XCTest が使えません。
そのため、チェックは `Tests/CalBarCoreTests` に置いた実行ファイルとして動かします。

## ディレクトリ構成

```
Package.swift
Sources/
├── CalBarCore/              # UI と OS に依存しないロジック
│   ├── Meeting.swift        # 予定のモデル
│   ├── MeetingLink.swift    # 会議 URL の抽出
│   ├── DayAgenda.swift      # 進行中・次の予定・参加対象・空き時間
│   ├── Countdown.swift      # 「15分後」などの表記と表示幅の計算
│   └── MenuBarStatus.swift  # メニューバーに出す内容
└── CalBar/                  # アプリ本体
    ├── CalBarApp.swift      # MenuBarExtra と設定ウィンドウ
    ├── AppModel.swift       # 状態管理・再読み込み・自動参加
    ├── CalendarService.swift    # EventKit からの読み込み
    ├── NotificationService.swift # 通知とアクション
    ├── GlobalHotKey.swift   # ⌃⌥J
    ├── Preferences.swift    # 設定（UserDefaults）
    ├── PreviewRenderer.swift # 画面の PNG 書き出し（デバッグ用）
    └── Views/
Tests/CalBarCoreTests/       # CalBarCore のチェック
Resources/                   # Info.plist とアイコン
scripts/build-app.sh         # .app のビルドとインストール
```

## 設定

設定は UserDefaults（`com.calbar.app`）に保存されます。
初回起動時に、旧版の `~/.calbar/config.json` から通知タイミング・自動参加・終日予定の表示を引き継ぎます。

| 項目 | 初期値 |
|------|--------|
| 通知のタイミング | 5 分前（開始時刻・1・3・5・10・15 分前から選択） |
| 開始時刻に会議 URL を自動で開く | オフ |
| メニューバーの表示内容 | タイトルと残り時間（開始時刻とタイトル・開始時刻と残り時間・開始時刻のみ・アイコンのみも選択可。開始時刻の形式は、会議中は「〜15:00」と終了時刻を表示） |
| タイトルの長さ | 短め（ノッチのあるメニューバーで隠れにくくするため） |
| 終日の予定 / 辞退した予定 / 空き時間の表示 | 表示 / 非表示 / 表示 |
| 表示するカレンダー | 誕生日以外のすべて |
| ⌃⌥J で次の会議に参加 | オン |

## v1（Python 版）からの変更点

v1 は Playwright で Google カレンダーの画面を読み取っていましたが、v2 では EventKit に置き換えました。
v1 には次の問題があり、画面の読み取りを続ける限り根本的には解決できなかったためです。

- 画面の表示が遅いと未ログインと判定され、ログイン用のブラウザが繰り返し開いていました。
- 終日予定が誤検出され、会議 URL が別の予定のものと取り違えられることがありました。
- 予定を 1 件ずつクリックして詳細を読むため、1 回の取得に約 40 秒かかっていました。

v1 のソースコードは Git の履歴に残っています。
`~/.calbar/` 配下のファイル（ブラウザのプロファイル、キャッシュ、ログ）は v2 では使わないため、不要なら削除してかまいません。
