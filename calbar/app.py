import logging
from collections import defaultdict
from datetime import datetime, date, timedelta

import rumps

from config import load_config, save_config
from models import AppConfig, Event, DaySchedule
from notifier import Notifier
from scheduler import FetchScheduler
from utils import (
    format_date_ja,
    format_minutes_remaining,
    open_url,
    truncate_title,
)

logger = logging.getLogger(__name__)


class CalBarApp(rumps.App):
    def __init__(self):
        super().__init__("\U0001f4c5", quit_button=None)
        self.config = load_config()
        self.events: dict[date, DaySchedule] = {}
        self.current_view_date: date = date.today()
        self.title = "\U0001f4c5 取得中..."

        # コンポーネント初期化
        self.notifier = Notifier(self.config)
        self.fetch_scheduler = FetchScheduler(self.config, self._on_events_updated)

        # 初回取得
        self.fetch_scheduler.run_fetch()

        # 定期更新タイマー
        self.fetch_timer = rumps.Timer(
            self._on_fetch_timer, self.config.fetch_interval_minutes * 60
        )
        self.fetch_timer.start()

        # メニューバータイトル更新タイマー（1分ごと）
        self.title_timer = rumps.Timer(self._update_title, 60)
        self.title_timer.start()

    def _on_events_updated(self, events: list[Event]):
        """予定取得完了時のコールバック"""
        # 日付ごとにグループ化
        day_events: dict[date, list[Event]] = defaultdict(list)
        for event in events:
            event_date = event.start_time.date()
            day_events[event_date].append(event)

        self.events = {}
        for d, evts in day_events.items():
            self.events[d] = DaySchedule(date=d, events=evts)

        # メニューバータイトル更新
        self._update_title()

        # メニュー再構築
        self._build_menu()

        # 当日の通知をスケジュール
        today = date.today()
        today_events = []
        for event in events:
            if event.start_time.date() == today:
                today_events.append(event)
        self.notifier.schedule_notifications(today_events)

        logger.info(f"予定を更新しました: {len(events)} 件")

    def _build_menu(self):
        """current_view_date に基づいてメニューを再構築"""
        self.menu.clear()
        schedule = self.events.get(self.current_view_date)
        date_str = format_date_ja(self.current_view_date)

        # 日付ヘッダー
        header = rumps.MenuItem(f"\u2500\u2500 {date_str} \u2500\u2500")
        header.set_callback(None)
        self.menu.add(header)
        self.menu.add(rumps.separator)

        if schedule:
            # 終日予定
            if self.config.show_all_day_events:
                for ev in schedule.all_day_events:
                    item = rumps.MenuItem(
                        f"\U0001f7e2 [\u7d42\u65e5] {ev.title}",
                        callback=lambda _, e=ev: self._open_meeting(e),
                    )
                    self.menu.add(item)

            if schedule.all_day_events and schedule.timed_events:
                self.menu.add(rumps.separator)

            # 時刻付き予定
            for ev in schedule.timed_events:
                label = self._format_event_label(ev)
                item = rumps.MenuItem(
                    label,
                    callback=lambda _, e=ev: self._open_meeting(e),
                )
                self.menu.add(item)
        else:
            self.menu.add(rumps.MenuItem("\u4e88\u5b9a\u306a\u3057"))

        # ナビゲーション
        self.menu.add(rumps.separator)
        self.menu.add(
            rumps.MenuItem("\u25c0 \u524d\u65e5", callback=self._prev_day)
        )
        self.menu.add(
            rumps.MenuItem("  \u4eca\u65e5", callback=self._go_today)
        )
        self.menu.add(
            rumps.MenuItem("\u7fcc\u65e5 \u25b6", callback=self._next_day)
        )

        # アクション
        self.menu.add(rumps.separator)
        self.menu.add(
            rumps.MenuItem(
                "\U0001f504 \u4eca\u3059\u3050\u66f4\u65b0",
                callback=self._manual_refresh,
            )
        )
        self.menu.add(
            rumps.MenuItem(
                "\u2699 \u8a2d\u5b9a...", callback=self._open_settings
            )
        )
        self.menu.add(rumps.separator)
        self.menu.add(
            rumps.MenuItem(
                "\u7d42\u4e86", callback=self._quit_app
            )
        )

    def _format_event_label(self, event: Event) -> str:
        """イベントをメニュー表示用にフォーマット"""
        start_str = event.start_time.strftime("%H:%M")
        end_str = event.end_time.strftime("%H:%M")
        title = event.title
        url_indicator = " \U0001f517" if event.meeting_url else ""
        return f"{start_str} - {end_str}  {title}{url_indicator}"

    def _update_title(self, _=None):
        """メニューバータイトルを次の予定で更新"""
        now = datetime.now()
        today_schedule = self.events.get(now.date())

        if not today_schedule:
            self.title = "\U0001f4c5 \u672c\u65e5\u306e\u4e88\u5b9a\u7d42\u4e86"
            return

        next_event = None
        for ev in today_schedule.timed_events:
            if ev.start_time > now:
                next_event = ev
                break

        if next_event:
            minutes_until = int(
                (next_event.start_time - now).total_seconds() / 60
            )
            title_text = truncate_title(
                next_event.title, self.config.max_title_length_menubar
            )
            time_str = next_event.start_time.strftime("%H:%M")
            remaining = format_minutes_remaining(minutes_until)
            self.title = f"\U0001f4c5 {time_str} {title_text} ({remaining})"
        else:
            self.title = "\U0001f4c5 \u672c\u65e5\u306e\u4e88\u5b9a\u7d42\u4e86"

    def _open_meeting(self, event: Event):
        """会議 URL をブラウザで開く"""
        if event.meeting_url:
            open_url(event.meeting_url)

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

    # アクション
    def _on_fetch_timer(self, _):
        """定期取得タイマーのコールバック"""
        self.fetch_scheduler.run_fetch()

    def _manual_refresh(self, _):
        """手動で予定を更新"""
        self.title = "\U0001f4c5 \u53d6\u5f97\u4e2d..."
        self.fetch_scheduler.run_fetch()

    def _open_settings(self, _):
        """設定ダイアログを表示"""
        # 通知時間の設定
        response = rumps.Window(
            title="\u901a\u77e5\u8a2d\u5b9a",
            message="\u4e88\u5b9a\u306e\u4f55\u5206\u524d\u306b\u901a\u77e5\u3057\u307e\u3059\u304b\uff1f",
            default_text=str(self.config.notification_minutes_before),
            ok="\u4fdd\u5b58",
            cancel="\u30ad\u30e3\u30f3\u30bb\u30eb",
            dimensions=(200, 24),
        ).run()

        if response.clicked:
            try:
                minutes = int(response.text.strip())
                if 0 <= minutes <= 60:
                    self.config.notification_minutes_before = minutes
                    save_config(self.config)
                    self.notifier.config = self.config
            except ValueError:
                pass

        # 取得間隔の設定
        response = rumps.Window(
            title="\u53d6\u5f97\u9593\u9694",
            message="\u30ab\u30ec\u30f3\u30c0\u30fc\u306e\u53d6\u5f97\u9593\u9694\uff08\u5206\uff09\u3092\u5165\u529b\u3057\u3066\u304f\u3060\u3055\u3044\uff081\u301c30\uff09:",
            default_text=str(self.config.fetch_interval_minutes),
            ok="\u4fdd\u5b58",
            cancel="\u30ad\u30e3\u30f3\u30bb\u30eb",
            dimensions=(200, 24),
        ).run()

        if response.clicked:
            try:
                interval = int(response.text.strip())
                if 1 <= interval <= 30:
                    self.config.fetch_interval_minutes = interval
                    save_config(self.config)
                    # タイマー再設定
                    self.fetch_timer.stop()
                    self.fetch_timer = rumps.Timer(
                        self._on_fetch_timer,
                        self.config.fetch_interval_minutes * 60,
                    )
                    self.fetch_timer.start()
            except ValueError:
                pass

    def _quit_app(self, _):
        """アプリ終了"""
        self.notifier.cancel_all()
        rumps.quit_application()
