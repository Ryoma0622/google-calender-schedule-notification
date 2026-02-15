# macOS メニューバー スケジュール管理アプリ — 設計書

## 1. プロジェクト概要

macOS のメニューバー（トップバー）に常駐し、Google カレンダーの予定をリアルタイムで表示・通知するネイティブデスクトップアプリケーション。Playwright を用いて Google カレンダーから予定を取得し、次のミーティング情報をメニューバーに常時表示する。

-----

## 2. 技術スタック

|レイヤー     |技術                                                                |選定理由                              |
|---------|------------------------------------------------------------------|----------------------------------|
|言語       |Python 3.11+                                                      |Playwright との親和性、rumps によるメニューバー統合|
|メニューバー UI|**rumps** (Ridiculously Uncomplicated macOS Python Statusbar apps)|軽量・シンプルな macOS ステータスバーアプリ構築       |
|カレンダー取得  |**Playwright** (Chromium)                                         |Google カレンダーの認証・スクレイピングを一元化       |
|通知       |macOS `UserNotifications`（**pync** / **terminal-notifier** 経由）    |macOS ネイティブ通知センター連携               |
|データ永続化   |JSON ファイル（`~/.calbar/`）                                           |設定保存・キャッシュ用途、軽量                   |
|パッケージング  |**py2app**                                                        |macOS .app バンドル化                  |

-----

## 3. システム構成図

```
┌─────────────────────────────────────────────────┐
│                   macOS Menu Bar                │
│  「📅 14:00 Weekly Standup (15分後)」            │
│         ↓ クリック                               │
│  ┌───────────────────────────────┐              │
│  │  ── 2026/02/14 (土) ──       │              │
│  │  09:00  朝会                  │              │
│  │  14:00  Weekly Standup  🔗    │              │
│  │  16:30  1on1 with Tanaka 🔗  │              │
│  │  ──────────────────────       │              │
│  │  ◀ 前日 │ 今日 │ 翌日 ▶      │              │
│  │  ──────────────────────       │              │
│  │  ⚙ 設定  │  🔄 更新          │              │
│  └───────────────────────────────┘              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              Background Services                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Scheduler │  │ Notifier │  │  Playwright  │  │
│  │ (定期取得)│  │ (通知)   │  │  (取得)      │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────┘
```

-----

## 4. 要件定義

### 4.1 機能要件

|ID  |機能名            |説明                                                                |優先度|
|----|---------------|------------------------------------------------------------------|---|
|F-01|Google カレンダー取得 |Playwright で Google Calendar を開き、1 週間分の予定を取得                      |必須 |
|F-02|認証ハンドリング       |初回起動時に Google 認証（ログインフロー）を Playwright ブラウザ上で実行。認証状態はブラウザプロファイルに永続化|必須 |
|F-03|メニューバー常駐表示     |次のミーティングの「時刻 + タイトル + 残り時間」をメニューバーに常時表示                           |必須 |
|F-04|当日予定一覧         |メニューバークリックで当日の時刻付き予定一覧をドロップダウン表示                                  |必須 |
|F-05|日付ナビゲーション      |「前日」「今日」「翌日」ボタンで別日の予定一覧に切り替え                                      |必須 |
|F-06|事前通知           |予定の N 分前に macOS 通知を表示（N は設定可能、デフォルト 5 分）                          |必須 |
|F-07|会議 URL ワンクリック起動|通知クリック時、予定に Google Meet / Zoom 等の URL が含まれる場合、ブラウザで自動的に開く         |必須 |
|F-08|設定画面           |通知タイミング（分数）、取得間隔、表示形式などの設定 UI                                     |必須 |
|F-09|手動更新           |メニューから手動でカレンダー再取得を実行可能                                            |必須 |
|F-10|終日予定の表示        |終日イベントは一覧の先頭に「終日」ラベル付きで表示                                         |推奨 |

### 4.2 非機能要件

|ID   |項目     |内容                                   |
|-----|-------|-------------------------------------|
|NF-01|対応 OS  |macOS 12 (Monterey) 以降               |
|NF-02|自動更新間隔 |デフォルト 5 分ごと（設定可能: 1〜30 分）            |
|NF-03|起動時間   |アプリ起動後 10 秒以内にメニューバー表示開始             |
|NF-04|メモリ使用量 |常駐時 200MB 以下（Playwright ヘッドレス含む）     |
|NF-05|認証永続化  |Chromium ユーザープロファイルにセッションを保存し、再認証を最小化|
|NF-06|オフライン耐性|ネットワーク不通時は最後に取得したキャッシュデータを表示         |

-----

## 5. 機能設計

### 5.1 ディレクトリ構成

```
calbar/
├── main.py                  # エントリーポイント（rumps アプリ起動）
├── app.py                   # CalBarApp クラス（rumps.App 継承、メニューバー制御）
├── calendar_fetcher.py      # Playwright による Google Calendar スクレイピング
├── event_parser.py          # スクレイピング結果 → Event データモデルへの変換
├── notifier.py              # macOS 通知の発行・会議 URL 起動
├── scheduler.py             # 定期取得のタイマー管理
├── config.py                # 設定の読み書き（JSON）
├── models.py                # データモデル定義
├── utils.py                 # ヘルパー関数
├── resources/
│   └── icon.png             # メニューバーアイコン（18x18 テンプレート画像）
├── requirements.txt
├── setup.py                 # py2app 設定
└── README.md
```

### 5.2 データモデル（models.py）

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Event:
    title: str
    start_time: datetime           # 終日予定の場合は当日 00:00:00
    end_time: datetime             # 終日予定の場合は翌日 00:00:00
    is_all_day: bool = False
    location: Optional[str] = None
    meeting_url: Optional[str] = None  # Google Meet / Zoom / Teams URL
    description: Optional[str] = None
    calendar_name: Optional[str] = None

@dataclass
class DaySchedule:
    date: datetime.date
    events: list[Event] = field(default_factory=list)

    @property
    def all_day_events(self) -> list[Event]:
        return [e for e in self.events if e.is_all_day]

    @property
    def timed_events(self) -> list[Event]:
        return sorted(
            [e for e in self.events if not e.is_all_day],
            key=lambda e: e.start_time
        )

@dataclass
class AppConfig:
    notification_minutes_before: int = 5       # 通知タイミング（分前）
    fetch_interval_minutes: int = 5            # 自動取得間隔
    browser_profile_path: str = "~/.calbar/browser_profile"
    cache_path: str = "~/.calbar/cache.json"
    config_path: str = "~/.calbar/config.json"
    show_all_day_events: bool = True
    max_title_length_menubar: int = 30         # メニューバー表示のタイトル文字数上限
```

### 5.3 カレンダー取得（calendar_fetcher.py）

#### 処理フロー

```
[起動 / 定期タイマー / 手動更新]
       │
       ▼
Playwright Chromium 起動（ヘッドレス）
  ※ ユーザープロファイルを指定して永続セッション利用
       │
       ▼
Google Calendar (https://calendar.google.com) にアクセス
       │
       ├── 認証済み → 予定取得ステップへ
       │
       └── 未認証 → ヘッドレス OFF でブラウザを可視化
                     → ユーザーに Google ログインを促す
                     → ログイン完了を検知（URL or DOM 判定）
                     → セッション保存 → 予定取得ステップへ
       │
       ▼
1 週間ビュー（Week View）に切り替え
       │
       ▼
DOM から各日・各予定を抽出
  - タイトル、開始時刻、終了時刻、終日フラグ
  - 予定詳細をクリック → Meet/Zoom URL を取得
       │
       ▼
Event オブジェクトのリストとして返却
       │
       ▼
JSON キャッシュに保存（オフライン用）
```

#### 認証判定ロジック

```python
async def is_authenticated(page) -> bool:
    """Google Calendar のメインビューが表示されているか判定"""
    try:
        # カレンダーのメインコンテナが存在するかを確認
        await page.wait_for_selector('[data-view-heading]', timeout=5000)
        return True
    except:
        return False
```

#### 認証フロー

```python
async def authenticate(playwright):
    """
    未認証時にヘッド付きブラウザを起動しユーザーに手動ログインさせる
    """
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir=config.browser_profile_path,
        headless=False,  # ユーザーに見えるブラウザを起動
        args=['--window-size=800,600']
    )
    page = browser.pages[0]
    await page.goto('https://calendar.google.com')

    # ログイン完了を待機（カレンダーメインビュー表示まで）
    # ユーザーが手動でログインするのを待つ
    await page.wait_for_selector('[data-view-heading]', timeout=300000)  # 5分待機

    await browser.close()
```

#### 予定抽出ロジック（概要）

```python
async def fetch_events(config: AppConfig) -> list[Event]:
    """1 週間分の予定を取得"""
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=config.browser_profile_path,
            headless=True
        )
        page = browser.pages[0]
        await page.goto('https://calendar.google.com/calendar/r/week')

        if not await is_authenticated(page):
            await browser.close()
            # 認証フローを呼び出し（headless=False で再起動）
            await authenticate(p)
            # 認証後にリトライ
            return await fetch_events(config)

        events = []

        # ====================================
        # Week ビューの DOM 解析
        # ====================================
        # 1. 終日イベント領域の抽出
        # 2. 時間指定イベントの抽出
        # 3. 各イベントをクリックし詳細パネルから追加情報取得:
        #    - 会議 URL (Google Meet / Zoom / Teams)
        #    - 場所
        #    - 説明

        # 実装時の注意:
        # Google Calendar の DOM 構造はクラス名がハッシュ化されるため
        # aria-label、data-* 属性、role 属性を優先的にセレクタに使用する

        await browser.close()
        return events
```

> **実装上の重要な注意点**:
> 
> - Google Calendar の DOM はクラス名が動的ハッシュ（例: `.pOLrzc`）になるため、**`aria-label`、`data-*` 属性、`role` 属性**をセレクタの基軸にすること。
> - 予定をクリック → 詳細ポップアップが開く → URL / 場所等を取得 → ポップアップを閉じる、というループを予定数分繰り返す。
> - ネットワークエラー時はキャッシュ（`~/.calbar/cache.json`）から読み込む。

### 5.4 会議 URL 抽出ロジック

予定の詳細テキスト・URL フィールドから以下のパターンを正規表現で検出する:

```python
import re

MEETING_URL_PATTERNS = [
    # Google Meet
    r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',
    # Zoom
    r'https://[\w.-]*zoom\.us/j/\d+(?:\?pwd=[\w]+)?',
    # Microsoft Teams
    r'https://teams\.microsoft\.com/l/meetup-join/[\w%.-]+',
    # Webex
    r'https://[\w.-]*\.webex\.com/[\w/.-]+',
]

def extract_meeting_url(text: str) -> Optional[str]:
    """テキストから最初にマッチした会議 URL を返す"""
    for pattern in MEETING_URL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None
```

### 5.5 メニューバー UI（app.py）

#### メニューバー表示仕様

**タイトル（常時表示テキスト）:**

|状態           |表示例                            |
|-------------|-------------------------------|
|次の予定あり       |`📅 14:00 Weekly Standup (15分後)`|
|次の予定あり（タイトル長）|`📅 14:00 プロジェクトキック... (15分後)`  |
|本日の残り予定なし    |`📅 本日の予定終了`                    |
|予定取得失敗       |`📅 ⚠ 更新エラー`                    |
|取得中          |`📅 取得中...`                     |

**ドロップダウンメニュー構成:**

```
────── 2026年2月14日（土）──────    ← 日付ヘッダー（クリック不可）
🟢 [終日] チームビルディング Day    ← 終日予定（ある場合のみ表示）
─────────────────────────────
09:00 - 09:30  朝会                 ← 通常予定（クリックでMeet/Zoom起動、URLがある場合）
14:00 - 15:00  Weekly Standup 🔗    ← 🔗 = 会議 URL あり
16:30 - 17:00  1on1 with Tanaka 🔗
─────────────────────────────
◀ 前日                             ← 日付ナビゲーション
  今日
翌日 ▶
─────────────────────────────
🔄 今すぐ更新                       ← 手動更新
⚙ 設定...                          ← 設定画面を開く
─────────────────────────────
終了                                ← アプリ終了
```

#### rumps 実装概要

```python
import rumps
import threading
from datetime import datetime, date, timedelta

class CalBarApp(rumps.App):
    def __init__(self):
        super().__init__("📅", quit_button=None)
        self.config = load_config()
        self.events: dict[date, DaySchedule] = {}
        self.current_view_date: date = date.today()

        # 初回取得
        self._start_fetch()

        # 定期更新タイマー
        self.timer = rumps.Timer(
            self._on_timer,
            self.config.fetch_interval_minutes * 60
        )
        self.timer.start()

        # メニューバータイトル更新タイマー（1分ごと）
        self.title_timer = rumps.Timer(self._update_title, 60)
        self.title_timer.start()

    def _build_menu(self):
        """current_view_date に基づいてメニューを再構築"""
        self.menu.clear()
        schedule = self.events.get(self.current_view_date)
        date_str = self.current_view_date.strftime('%Y年%m月%d日（%a）')

        self.menu.add(rumps.MenuItem(f"── {date_str} ──", callback=None))
        self.menu.add(rumps.separator)

        if schedule:
            # 終日予定
            for ev in schedule.all_day_events:
                self.menu.add(rumps.MenuItem(
                    f"🟢 [終日] {ev.title}",
                    callback=lambda _, e=ev: self._open_meeting(e)
                ))
            # 時刻付き予定
            for ev in schedule.timed_events:
                label = self._format_event_label(ev)
                self.menu.add(rumps.MenuItem(
                    label,
                    callback=lambda _, e=ev: self._open_meeting(e)
                ))
        else:
            self.menu.add(rumps.MenuItem("予定なし"))

        # ナビゲーション
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("◀ 前日", callback=self._prev_day))
        self.menu.add(rumps.MenuItem("  今日", callback=self._go_today))
        self.menu.add(rumps.MenuItem("翌日 ▶", callback=self._next_day))

        # アクション
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🔄 今すぐ更新", callback=self._manual_refresh))
        self.menu.add(rumps.MenuItem("⚙ 設定...", callback=self._open_settings))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("終了", callback=rumps.quit_application))

    def _update_title(self, _=None):
        """メニューバータイトルを次の予定で更新"""
        now = datetime.now()
        today_schedule = self.events.get(now.date())

        if not today_schedule:
            self.title = "📅 本日の予定終了"
            return

        next_event = None
        for ev in today_schedule.timed_events:
            if ev.start_time > now:
                next_event = ev
                break

        if next_event:
            minutes_until = int((next_event.start_time - now).total_seconds() / 60)
            title_text = next_event.title[:self.config.max_title_length_menubar]
            if len(next_event.title) > self.config.max_title_length_menubar:
                title_text += "..."
            time_str = next_event.start_time.strftime('%H:%M')
            self.title = f"📅 {time_str} {title_text} ({minutes_until}分後)"
        else:
            self.title = "📅 本日の予定終了"

    # 日付ナビゲーション
    def _prev_day(self, _):
        self.current_view_date -= timedelta(days=1)
        self._build_menu()

    def _next_day(self, _):
        self.current_view_date += timedelta(days=1)
        self._build_menu()

    def _go_today(self, _):
        self.current_view_date = date.today()
        self._build_menu()
```

### 5.6 通知（notifier.py）

#### 通知タイミング管理

```python
import subprocess
import threading
from datetime import datetime, timedelta

class Notifier:
    def __init__(self, config: AppConfig):
        self.config = config
        self._scheduled_timers: dict[str, threading.Timer] = {}

    def schedule_notifications(self, events: list[Event]):
        """全予定に対して通知タイマーをセット"""
        self.cancel_all()
        now = datetime.now()

        for event in events:
            if event.is_all_day:
                continue

            notify_at = event.start_time - timedelta(
                minutes=self.config.notification_minutes_before
            )

            if notify_at <= now:
                continue  # 既に通知時刻を過ぎている

            delay = (notify_at - now).total_seconds()
            timer_key = f"{event.title}_{event.start_time.isoformat()}"

            timer = threading.Timer(delay, self._send_notification, args=[event])
            timer.daemon = True
            timer.start()
            self._scheduled_timers[timer_key] = timer

    def _send_notification(self, event: Event):
        """macOS 通知を送信"""
        title = f"📅 {event.start_time.strftime('%H:%M')} {event.title}"
        minutes = self.config.notification_minutes_before
        message = f"{minutes}分後に開始します"

        if event.meeting_url:
            message += "\nクリックして会議に参加"

        # terminal-notifier を使用（Homebrew でインストール）
        cmd = [
            'terminal-notifier',
            '-title', title,
            '-message', message,
            '-sound', 'default',
            '-group', f'calbar-{event.start_time.isoformat()}',
        ]

        if event.meeting_url:
            cmd.extend(['-open', event.meeting_url])

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            # terminal-notifier がない場合、osascript フォールバック
            self._send_notification_osascript(event)

    def _send_notification_osascript(self, event: Event):
        """osascript によるフォールバック通知"""
        title = f"{event.start_time.strftime('%H:%M')} {event.title}"
        minutes = self.config.notification_minutes_before
        message = f"{minutes}分後に開始します"

        script = f'''
        display notification "{message}" with title "{title}" sound name "default"
        '''
        subprocess.run(['osascript', '-e', script])

        # 会議 URL がある場合は自動で開く
        if event.meeting_url:
            subprocess.run(['open', event.meeting_url])

    def cancel_all(self):
        """全タイマーをキャンセル"""
        for timer in self._scheduled_timers.values():
            timer.cancel()
        self._scheduled_timers.clear()
```

#### 通知 → 会議 URL 起動フロー

```
通知表示
  │
  ├── terminal-notifier 使用時
  │     └── 通知クリック → -open オプションで URL を直接起動
  │
  └── osascript フォールバック時
        └── 通知表示と同時に `open <URL>` で起動
              （osascript はクリックイベントを検知できないため）
```

### 5.7 設定管理（config.py）

```python
import json
import os
from models import AppConfig

CONFIG_DIR = os.path.expanduser("~/.calbar")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "notification_minutes_before": 5,
    "fetch_interval_minutes": 5,
    "show_all_day_events": True,
    "max_title_length_menubar": 30,
}

def load_config() -> AppConfig:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = {**DEFAULT_CONFIG, **json.load(f)}
            return AppConfig(**data)
    return AppConfig(**DEFAULT_CONFIG)

def save_config(config: AppConfig):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({
            "notification_minutes_before": config.notification_minutes_before,
            "fetch_interval_minutes": config.fetch_interval_minutes,
            "show_all_day_events": config.show_all_day_events,
            "max_title_length_menubar": config.max_title_length_menubar,
        }, f, indent=2)
```

### 5.8 設定ダイアログ

rumps の `rumps.Window` を使ったシンプルな設定入力:

```python
def _open_settings(self, _):
    """設定ダイアログを表示"""
    # 通知時間の設定
    response = rumps.Window(
        title="通知設定",
        message="予定の何分前に通知しますか？",
        default_text=str(self.config.notification_minutes_before),
        ok="保存",
        cancel="キャンセル",
        dimensions=(200, 24)
    ).run()

    if response.clicked:
        try:
            minutes = int(response.text.strip())
            if 0 <= minutes <= 60:
                self.config.notification_minutes_before = minutes
                save_config(self.config)
        except ValueError:
            pass

    # 取得間隔の設定
    response = rumps.Window(
        title="取得間隔",
        message="カレンダーの取得間隔（分）を入力してください（1〜30）:",
        default_text=str(self.config.fetch_interval_minutes),
        ok="保存",
        cancel="キャンセル",
        dimensions=(200, 24)
    ).run()

    if response.clicked:
        try:
            interval = int(response.text.strip())
            if 1 <= interval <= 30:
                self.config.fetch_interval_minutes = interval
                save_config(self.config)
                # タイマー再設定
                self.timer.stop()
                self.timer = rumps.Timer(
                    self._on_timer,
                    self.config.fetch_interval_minutes * 60
                )
                self.timer.start()
        except ValueError:
            pass
```

### 5.9 定期取得スケジューラ（scheduler.py）

```python
import asyncio
import threading
import json
import os
from datetime import date

class FetchScheduler:
    def __init__(self, config, on_events_updated):
        self.config = config
        self.on_events_updated = on_events_updated  # コールバック

    def run_fetch(self):
        """バックグラウンドスレッドで Playwright 取得を実行"""
        thread = threading.Thread(target=self._fetch_thread, daemon=True)
        thread.start()

    def _fetch_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            events = loop.run_until_complete(fetch_events(self.config))
            self._cache_events(events)
            self.on_events_updated(events)
        except Exception as e:
            # ネットワークエラー等 → キャッシュから読み込み
            cached = self._load_cache()
            if cached:
                self.on_events_updated(cached)
        finally:
            loop.close()

    def _cache_events(self, events):
        """取得結果を JSON キャッシュに保存"""
        cache_path = os.path.expanduser(self.config.cache_path)
        data = [
            {
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "is_all_day": e.is_all_day,
                "location": e.location,
                "meeting_url": e.meeting_url,
                "description": e.description,
            }
            for e in events
        ]
        with open(cache_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_cache(self):
        """キャッシュから予定を読み込み"""
        cache_path = os.path.expanduser(self.config.cache_path)
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                return json.load(f)
        return None
```

-----

## 6. 処理シーケンス

### 6.1 起動シーケンス

```
アプリ起動 (main.py)
  │
  ├─ 1. 設定読み込み (~/.calbar/config.json)
  │
  ├─ 2. rumps.App 初期化 → メニューバーにアイコン表示
  │     └─ タイトル: "📅 取得中..."
  │
  ├─ 3. バックグラウンドスレッドで Playwright 起動
  │     ├── Chromium 起動 (persistent context, headless=True)
  │     ├── calendar.google.com にアクセス
  │     │
  │     ├── [認証チェック]
  │     │   ├── 認証済み → 予定取得へ
  │     │   └── 未認証 → headless=False で再起動
  │     │        → macOS 通知: "Google アカウントにログインしてください"
  │     │        → ブラウザウィンドウ表示
  │     │        → ユーザーがログイン
  │     │        → ログイン完了検知
  │     │        → ブラウザ閉じる → headless=True で再接続
  │     │
  │     ├── Week ビューで DOM 解析
  │     ├── 7 日分の Event リスト生成
  │     ├── キャッシュに保存
  │     └── コールバック → メインスレッドに通知
  │
  ├─ 4. メニューバータイトル更新（次の予定表示）
  │
  ├─ 5. 通知タイマーセット（当日の全予定）
  │
  └─ 6. 定期取得タイマー開始（N 分間隔）
```

### 6.2 通知 → 会議参加シーケンス

```
予定の N 分前
  │
  ├─ Notifier がタイマー発火
  │
  ├─ macOS 通知表示
  │   タイトル: "📅 14:00 Weekly Standup"
  │   本文:    "5分後に開始します"
  │            "クリックして会議に参加"
  │
  └─ ユーザーが通知をクリック
      │
      ├── meeting_url あり → `open <URL>` でブラウザ起動
      │   (Google Meet / Zoom / Teams が開く)
      │
      └── meeting_url なし → 何もしない（通知を閉じるだけ）
```

-----

## 7. セットアップ手順（README 向け）

```bash
# 1. リポジトリのクローン
git clone <repo-url> && cd calbar

# 2. Python 仮想環境
python3 -m venv .venv && source .venv/bin/activate

# 3. 依存パッケージ
pip install -r requirements.txt

# 4. Playwright ブラウザインストール
playwright install chromium

# 5. terminal-notifier（通知用、推奨）
brew install terminal-notifier

# 6. 起動
python main.py
```

**requirements.txt:**

```
rumps>=0.4.0
playwright>=1.40.0
pync>=2.0.0
```

-----

## 8. 既知の制約・リスク

|#|リスク                   |影響              |対策                                        |
|-|----------------------|----------------|------------------------------------------|
|1|Google Calendar DOM 変更|スクレイピングが壊れる     |aria-label / role ベースのセレクタを使用。変更検知でエラー通知  |
|2|Playwright のメモリ消費     |常駐で 100-200MB 消費|取得完了後にブラウザを毎回閉じ、次回取得時に再起動する設計も検討          |
|3|2FA / CAPTCHA         |自動認証が困難         |初回のみヘッド付きで手動認証。セッション永続化で頻度を最小化            |
|4|通知クリック（osascript）     |クリックイベントを取得できない |terminal-notifier 推奨。フォールバック時は通知と同時にURLを開く|
|5|複数 Google アカウント       |どのアカウントの予定か不明確  |v1 では単一アカウントのみ対応。将来的に選択機能追加               |

-----

## 9. 将来の拡張候補（スコープ外）

- **Google Calendar API への移行**: OAuth2 + REST API による安定取得
- **複数アカウント対応**: アカウント切り替え機能
- **予定の作成・編集**: メニューバーから新規予定を追加
- **カスタムテーマ**: ダーク/ライトモード切り替え
- **Homebrew Formula**: `brew install calbar` でインストール可能に
- **ログイン不要モード**: ICS URL（公開カレンダー）からの取得対応
