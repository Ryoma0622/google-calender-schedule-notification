# Agent State Document — CalBar デバッグ引き継ぎ

> 最終更新: 2026-02-15
> ブランチ: `claude/google-calendar-notifications-463V9`

---

## 1. プロジェクト概要

macOS メニューバーに常駐する Google カレンダー通知アプリ。
Playwright で Google Calendar をスクレイピングし、rumps でメニューバー UI を構築する。

## 2. 解決済みの問題

### 2-1. Google ログインがブロックされる
- **原因:** Playwright が自動化フラグを付与 → Google が「安全でないブラウザ」として拒否
- **対処:** `--disable-blink-features=AutomationControlled` + `ignore_default_args=["--enable-automation"]`
- **コミット:** `656590e`, `69a9aad`

### 2-2. SingletonLock で Chromium 起動失敗
- **原因:** persistent context が正常終了しないと `SingletonLock` が残留
- **対処:** `_remove_singleton_lock()` で起動前に削除
- **コミット:** `84fe2ee`

### 2-3. `channel="chrome"` → Chromium に戻す
- **経緯:** Google ログインブロック回避のため一時的に system Chrome (`channel="chrome"`) を使用したが、既に起動中の Chrome とプロファイル競合（SingletonLock）が発生。認証ブロックは上記フラグで解決済みだったため、Chromium に戻した
- **コミット:** `0a9f25d`

### 2-4. `page.goto` タイムアウト (networkidle)
- **原因:** Google Calendar は SPA で常にバックグラウンド通信 → `networkidle` に到達しない
- **対処:** `wait_until="domcontentloaded"` に変更。カレンダー描画確認は既存の `is_authenticated()` の `[data-view-heading]` 待ちが担保
- **コミット:** `561013f`

### 2-5. バックグラウンドスレッドからの UI 更新
- **原因:** `FetchScheduler._fetch_thread` → `_on_events_updated` でメインスレッド外から `self.title` / `self.menu` (AppKit) を操作 → 更新がサイレントに無視される
- **対処:** ポーリング方式に変更。`_on_events_fetched` (BG) はデータ保持のみ、`_poll_pending_events` (1秒 rumps.Timer = メインスレッド) が UI 更新
- **コミット:** `dab6b35`

## 3. 現在の未解決問題: メニューバーに何も表示されない

### 症状
- `uv run calbar/main.py` でプロセスは正常起動
- ログに `1 件の予定を取得しました` / `予定を更新しました` と出る
- しかし macOS メニューバーにアイコン・テキストが一切表示されない
- スレッドの修正（`dab6b35`）後も変化なし

### 調査すべきポイント

1. **rumps.App が NSStatusItem を生成できているか**
   - `super().__init__("📅", quit_button=None)` → `app.run()` で NSApplication が起動しているか
   - ターミナルから Python スクリプトとして起動すると LSUIElement/NSApplication の登録が不十分な可能性
   - rumps は内部的に `NSApplication.sharedApplication()` を使うが、macOS 13+ では追加の権限やバンドル設定が必要な場合がある

2. **rumps.Timer が `app.run()` 前に `start()` されている**
   - `__init__` 内で `self._poll_timer.start()` / `self.fetch_timer.start()` / `self.title_timer.start()` を呼んでいる
   - NSTimer は RunLoop がないと機能しないが、`app.run()` は `__init__` 完了後に呼ばれる
   - Timer の start を `app.run()` 後に遅延させる必要があるか確認（rumps の `@rumps.timer()` デコレータは内部で遅延登録する）

3. **初期表示 `"📅 取得中..."` すら出ない点**
   - バックグラウンドスレッドの問題なら、少なくとも初期タイトルは表示されるはず
   - 初期タイトルも出ないなら rumps/NSStatusItem レベルの問題

4. **デバッグ方法案**
   - 最小限の rumps アプリでメニューバー表示を確認:
     ```python
     import rumps
     app = rumps.App("Test", title="Hello")
     app.run()
     ```
   - これが動けば rumps は正常 → CalBarApp の `__init__` 内に問題
   - これも動かなければ環境（macOS バージョン、Python、rumps バージョン）の問題

5. **`quit_button=None` の影響**
   - rumps のデフォルト quit ボタンを無効化している
   - メニューが完全に空の状態で NSStatusItem が表示されるか確認
   - `quit_button=None` を外して試す

## 4. ファイル構成と変更箇所

| ファイル | 役割 | 最近の変更 |
|---------|------|-----------|
| `calbar/main.py` | エントリーポイント | PEP 723 メタデータ追加 |
| `calbar/app.py` | rumps メニューバー UI | **スレッド安全なポーリング方式に変更** |
| `calbar/calendar_fetcher.py` | Playwright スクレイピング | **Chromium に戻す、domcontentloaded、自動化フラグ** |
| `calbar/scheduler.py` | BG スレッド取得 + キャッシュ | 変更なし |
| `calbar/models.py` | Event, DaySchedule, AppConfig | 変更なし |
| `calbar/notifier.py` | macOS 通知 | 変更なし |
| `calbar/config.py` | 設定読み書き | 変更なし |
| `calbar/utils.py` | ヘルパー関数 | 変更なし |
| `calbar/event_parser.py` | DOM データ → Event 変換 | 変更なし |

## 5. コミット履歴（新しい順）

```
dab6b35 fix: dispatch UI updates to main thread via rumps.Timer polling
561013f fix: use domcontentloaded instead of networkidle for page.goto
0a9f25d fix: revert to Playwright Chromium, keep anti-automation flags
84fe2ee fix: remove stale SingletonLock before launching Chrome
656590e fix: disable automation flags to bypass Google's browser check
69a9aad fix: open Google login page directly for authentication
7883e6f fix: use system Chrome instead of bundled Chromium for Google login
67a30ad feat: support `uv run` with PEP 723 inline script metadata
3e53059 docs: add README.md and CLAUDE.md
681680a feat: implement macOS menu bar Google Calendar notification app
```

## 6. 開発環境

```bash
# 起動
uv run calbar/main.py

# Playwright Chromium インストール（初回）
uv run --with playwright playwright install chromium
```

## 7. 次のエージェントへの推奨アクション

1. まず最小 rumps アプリでメニューバー表示が動くか確認
2. 動かないなら rumps/macOS 環境の問題を調査
3. 動くなら CalBarApp の `__init__` を段階的にコメントアウトして原因特定
4. 特に `rumps.Timer.start()` の呼び出しタイミング（`app.run()` 前 vs 後）を疑う
5. `quit_button=None` を一時的に外してみる
