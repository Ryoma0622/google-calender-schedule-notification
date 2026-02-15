# Agent State Document — バンドルアプリ Playwright ブラウザパス修正

> 最終更新: 2026-02-15
> ブランチ: `main`

---

## 1. Task Overview

バンドルアプリ（`.app`）として配布した場合に Playwright が Chromium を見つけられずエラーになる問題を修正する。

エラー: `BrowserType.launch_persistent_context: Executable doesn't exist at .../CalBar.app/Contents/Resources/lib/python3.13/playwright/driver/package/.local-browsers/chromium_headless_shell-1208/...`

## 2. Plan / TODO

- [x] 原因調査: Playwright がバンドル内のパスでブラウザを探している理由を特定
- [x] `PLAYWRIGHT_BROWSERS_PATH` の設定を macOS 対応に修正（`~/Library/Caches/ms-playwright`）
- [x] 配布先でブラウザ未インストール時の自動インストール機能を追加
- [x] AGENT_STATE.md を更新

## 3. Progress / Completed Work

### 変更したファイル: `calbar/calendar_fetcher.py`

1. **ブラウザパス解決ロジック (L13-27)**: macOS と Linux 両方のパスを探索するように修正
   - 旧: `~/.cache/ms-playwright` のみ（Linux パス）
   - 新: `~/Library/Caches/ms-playwright`（macOS）→ `~/.cache/ms-playwright`（Linux）の順で探索
   - どちらも存在しない場合は macOS のデフォルトパスを設定

2. **Chromium 自動インストール機能 (L38-79)**: `_ensure_chromium_installed()` 関数を追加
   - バンドル内の node + cli.js を使って `playwright install chromium` を実行
   - `fetch_events` と `authenticate` の冒頭で呼び出し
   - 一度チェック済みならスキップ（`_chromium_checked` フラグ）

3. **`import subprocess` を追加**（自動インストール用）

### 根本原因

- Playwright はブラウザを `PLAYWRIGHT_BROWSERS_PATH` または `playwright/driver/package/.local-browsers/` から探す
- py2app でバンドルすると、playwright パッケージの位置が `.app` 内になり、`.local-browsers` もバンドル内を参照
- バンドルにはブラウザバイナリ（数百MB）は含まれないため、外部パスの設定が必要
- 既存コードは Linux パス（`~/.cache/ms-playwright`）のみ対応していたが、macOS では `~/Library/Caches/ms-playwright` に Playwright がブラウザをインストールする

## 4. Open Issues / Blockers

なし

## 5. Next Steps

コミット待ち。必要に応じてバンドルを再ビルドして動作確認。
