# CalBar - macOS メニューバー Google カレンダー通知アプリ

macOS のメニューバーに常駐し、Google カレンダーの予定をリアルタイムで表示・通知するデスクトップアプリケーション。
Playwright で Google カレンダーから予定を取得し、次のミーティング情報をメニューバーに常時表示します。

## 機能

- **メニューバー常駐表示** — 次の予定の時刻・タイトル・残り時間を常時表示
- **当日予定一覧** — メニューバークリックでドロップダウン表示
- **日付ナビゲーション** — 前日 / 今日 / 翌日の切り替え
- **事前通知** — 予定の N 分前に macOS 通知（デフォルト 5 分）
- **会議 URL ワンクリック起動** — 通知クリックで Google Meet / Zoom / Teams を自動起動
- **終日予定の表示** — 一覧の先頭に「終日」ラベル付きで表示
- **オフライン対応** — ネットワーク不通時はキャッシュデータを表示
- **設定画面** — 通知タイミング・取得間隔をカスタマイズ

## 表示イメージ

```
📅 14:00 Weekly Standup (15分後)
┌───────────────────────────────┐
│  ── 2026年2月14日（土）──       │
│  🟢 [終日] チームビルディング Day │
│  ─────────────────────        │
│  09:00 - 09:30  朝会           │
│  14:00 - 15:00  Weekly Standup 🔗 │
│  16:30 - 17:00  1on1 with Tanaka 🔗 │
│  ─────────────────────        │
│  ◀ 前日 │ 今日 │ 翌日 ▶       │
│  ─────────────────────        │
│  🔄 今すぐ更新                  │
│  ⚙ 設定...                    │
│  終了                          │
└───────────────────────────────┘
```

## 必要環境

- macOS 12 (Monterey) 以降
- Python 3.11+
- Google Chrome（Playwright がシステム Chrome を使用）
- [terminal-notifier](https://github.com/julienXX/terminal-notifier)（推奨、なくても動作可）

## セットアップ

### uv を使う場合（推奨）

依存関係は PEP 723 インラインメタデータで `main.py` に記述済みのため、`uv run` だけで起動できます。

```bash
# 1. リポジトリのクローン
git clone <repo-url> && cd google-calender-schedule-notification

# 2. terminal-notifier（通知用、推奨）
brew install terminal-notifier

# 3. 起動
uv run calbar/main.py
```

### 手動 venv の場合

```bash
# 1. リポジトリのクローン
git clone <repo-url> && cd google-calender-schedule-notification

# 2. Python 仮想環境
cd calbar
python3 -m venv .venv
source .venv/bin/activate

# 3. 依存パッケージ
pip install -r requirements.txt

# 4. terminal-notifier（通知用、推奨）
brew install terminal-notifier

# 5. 起動
python main.py
```

> **Note:** `playwright install` は不要です。`channel="chrome"` 指定によりシステムの Google Chrome を直接使用します。

## 初回起動時の認証

初回起動時、Google アカウントへのログインが必要です。

1. アプリがシステムの Google Chrome を可視モードで起動します
2. 表示されたブラウザで Google アカウントにログインしてください
3. Google カレンダーが表示されたら認証完了です（ブラウザは自動で閉じます）
4. 以降はセッションが `~/.calbar/browser_profile` に保存され、再認証なしで動作します

## 設定

設定は `~/.calbar/config.json` に保存されます。メニューの「⚙ 設定...」から変更できます。

| 項目 | デフォルト値 | 説明 |
|------|-----------|------|
| `notification_minutes_before` | `5` | 予定の何分前に通知するか（0〜60） |
| `fetch_interval_minutes` | `5` | カレンダーの自動取得間隔（1〜30 分） |
| `show_all_day_events` | `true` | 終日予定を表示するか |
| `max_title_length_menubar` | `30` | メニューバーのタイトル文字数上限 |

## ディレクトリ構成

```
calbar/
├── main.py                  # エントリーポイント
├── app.py                   # メニューバー UI（rumps.App）
├── calendar_fetcher.py      # Playwright による Google Calendar スクレイピング
├── event_parser.py          # スクレイピング結果 → Event 変換
├── notifier.py              # macOS 通知の発行・会議 URL 起動
├── scheduler.py             # 定期取得のタイマー管理・キャッシュ
├── config.py                # 設定の読み書き（JSON）
├── models.py                # データモデル定義
├── utils.py                 # ヘルパー関数
├── resources/               # メニューバーアイコン等
├── requirements.txt
└── setup.py                 # py2app 設定
```

## .app バンドルの作成

```bash
cd calbar
python setup.py py2app
```

`dist/CalBar.app` が生成されます。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| 言語 | Python 3.11+ |
| メニューバー UI | [rumps](https://github.com/jaredks/rumps) |
| カレンダー取得 | [Playwright](https://playwright.dev/python/) (システム Chrome) |
| 通知 | terminal-notifier / osascript フォールバック |
| データ永続化 | JSON ファイル (`~/.calbar/`) |
| パッケージング | py2app |

## 既知の制約

- Google Calendar の DOM 構造が変更されるとスクレイピングが壊れる可能性があります（aria-label / role ベースのセレクタで対策済み）
- Playwright ヘッドレス動作時のメモリ消費は 100〜200MB 程度です
- 2FA / CAPTCHA が必要な場合は初回手動認証が必要です
- v1 では単一 Google アカウントのみ対応しています
