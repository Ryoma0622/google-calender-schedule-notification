# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際のガイドです。

## プロジェクト概要

CalBar — macOS メニューバーに常駐する Google カレンダー通知アプリ。
Playwright で Google Calendar をスクレイピングし、rumps でメニューバー UI を構築する。

## ディレクトリ構造

- `calbar/` — アプリケーション本体
- `spec.md` — 設計書（要件定義・機能設計の原本）

## 開発環境セットアップ・起動

```bash
# uv で起動（依存は PEP 723 インラインメタデータから自動解決）
uv run calbar/main.py
```

`playwright install` は不要（`channel="chrome"` でシステムの Google Chrome を使用）。

### 手動 venv の場合

```bash
cd calbar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## アーキテクチャ

```
main.py → app.py (CalBarApp: rumps.App)
              ├── scheduler.py (FetchScheduler) → calendar_fetcher.py (Playwright)
              │                                    └── event_parser.py
              ├── notifier.py (Notifier)
              ├── config.py (load/save)
              └── models.py (Event, DaySchedule, AppConfig)
```

- **app.py**: メインの UI ロジック。rumps.App を継承した `CalBarApp` クラス。メニュー構築、日付ナビゲーション、設定ダイアログを担当
- **calendar_fetcher.py**: Playwright で Google Calendar の Week ビュー DOM を解析。認証フロー（headless=False で手動ログイン）も担当
- **event_parser.py**: DOM から取得した生データを `Event` オブジェクトに変換。時刻パース処理
- **scheduler.py**: バックグラウンドスレッドで Playwright 取得を実行。JSON キャッシュ（`~/.calbar/cache.json`）の読み書き
- **notifier.py**: `threading.Timer` で通知をスケジュール。terminal-notifier → osascript のフォールバック
- **config.py**: `~/.calbar/config.json` の読み書き
- **models.py**: `Event`, `DaySchedule`, `AppConfig` のデータクラス
- **utils.py**: 会議 URL 抽出（Meet/Zoom/Teams/Webex の正規表現）、日付フォーマット等のヘルパー

## 重要な設計判断

- Google Calendar の DOM はクラス名が動的ハッシュのため、`aria-label`・`data-*`・`role` 属性をセレクタの基軸にする
- Playwright バンドル版 Chromium では Google ログインがブロックされるため、`channel="chrome"` でシステム Chrome を使用
- 認証状態は Chrome の persistent context（`~/.calbar/browser_profile`）で永続化
- Playwright の操作はバックグラウンドスレッドで非同期実行し、rumps のメインループをブロックしない
- ネットワーク障害時はキャッシュから予定を読み込む
- 通知は terminal-notifier を優先し、未インストール時は osascript にフォールバック

## データの保存先

すべてのデータは `~/.calbar/` 配下:

| ファイル | 用途 |
|---------|------|
| `config.json` | ユーザー設定 |
| `cache.json` | 予定のキャッシュ（オフライン用） |
| `browser_profile/` | Chrome セッション（認証永続化） |
| `calbar.log` | アプリケーションログ |

## コーディング規約

- Python 3.11+ の型ヒントを使用
- データクラスは `dataclasses.dataclass` で定義
- 日本語の UI テキストはソースコード内に直接記述（i18n 非対応）
- ロギングは `logging` モジュールを使用（`print` は使わない）
