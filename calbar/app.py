import logging
import os
import threading
import unicodedata
from collections import defaultdict
from datetime import datetime, date, timedelta

import rumps

from config import load_config, save_config
from models import AppConfig, Event, DaySchedule
from notifier import Notifier
from scheduler import FetchScheduler
from utils import (
    format_date_ja,
    open_url,
)

logger = logging.getLogger(__name__)


class CalBarApp(rumps.App):
    def __init__(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resources",
            "icon.png",
        )
        super().__init__(
            "CalBar",
            title="Cal",
            icon=icon_path if os.path.exists(icon_path) else None,
            quit_button=None,
        )
        self._icon_path = icon_path
        self.config = load_config()
        self.events: dict[date, DaySchedule] = {}
        self.current_view_date: date = date.today()
        self._started = False
        self._status_backend_logged = False
        self._status_refresh_count = 0
        self._watchdog_tick_count = 0

        # バックグラウンドスレッド → メインスレッド間のイベント受け渡し
        self._pending_events: list[Event] | None = None
        self._events_lock = threading.Lock()

        # コンポーネント初期化
        self.notifier = Notifier(self.config)
        self.fetch_scheduler = FetchScheduler(self.config, self._on_events_fetched)

        # 初期メニューを構築（起動直後に空メニューにならないようにする）
        self._build_menu()

        # 起動後に開始するタイマー（run loop が開始するまでは start しない）
        self._poll_timer = rumps.Timer(self._poll_pending_events, 1)
        self.fetch_timer = rumps.Timer(
            self._on_fetch_timer, self.config.fetch_interval_minutes * 60
        )
        self.title_timer = rumps.Timer(self._update_title, 60)
        self.status_watchdog_timer = rumps.Timer(self._status_watchdog, 15)

        # rumps の run loop 起動後に初回取得とタイマー開始を行う
        rumps.events.before_start(self._on_before_start)

    def _on_before_start(self):
        """run loop 開始直前（メインスレッド）に初期化処理を開始"""
        if self._started:
            return
        self._started = True
        logger.info("メニューバー初期化完了。タイマーと予定取得を開始します")

        self._poll_timer.start()
        self.fetch_timer.start()
        self.title_timer.start()
        self.status_watchdog_timer.start()
        self.fetch_scheduler.run_fetch()
        self._force_status_item_refresh()

    def _force_status_item_refresh(self):
        """ステータスアイテム表示を AppKit に直接再反映する。

        一部環境では rumps の setTitle_ 経由反映が表示に出ないケースがあるため、
        NSStatusItem.button() が利用可能ならこちらにもタイトルを明示セットする。
        """
        nsapp = getattr(self, "_nsapp", None)
        if nsapp is None or not hasattr(nsapp, "nsstatusitem"):
            return

        status_item = nsapp.nsstatusitem
        title = self.title or ""
        display_title = "●" if os.getenv("CALBAR_DEBUG_DOT_TITLE") == "1" else title
        try:
            if hasattr(status_item, "button"):
                button = status_item.button()
            else:
                button = None

            if button is not None:
                button.setTitle_(display_title)
                if not button.title() and not button.image():
                    if os.path.exists(self._icon_path) and hasattr(button, "setImage_"):
                        try:
                            from AppKit import NSImage
                            image = NSImage.alloc().initByReferencingFile_(self._icon_path)
                            if image is not None:
                                if hasattr(image, "setTemplate_"):
                                    image.setTemplate_(True)
                                button.setImage_(image)
                        except Exception:
                            logger.debug("ステータスアイコン設定に失敗しました", exc_info=True)
                    button.setTitle_(self.name)
                if hasattr(button, "setToolTip_"):
                    button.setToolTip_(title)
                if not self._status_backend_logged:
                    logger.info("ステータス表示: NSStatusItem.button() 経由で反映")
                    self._status_backend_logged = True
            else:
                status_item.setTitle_(display_title)
                if not status_item.title() and not status_item.image():
                    status_item.setTitle_(self.name)
                if not self._status_backend_logged:
                    logger.info("ステータス表示: NSStatusItem 直接 API で反映")
                    self._status_backend_logged = True

            if hasattr(status_item, "setVisible_"):
                status_item.setVisible_(True)
            if hasattr(status_item, "setLength_"):
                # 固定幅はメニューバー混雑時に項目が押し出されやすいため可変幅を使う。
                # NSVariableStatusItemLength = -1.0
                status_item.setLength_(-1.0)

            self._status_refresh_count += 1
            if self._status_refresh_count <= 3:
                visible = (
                    status_item.isVisible()
                    if hasattr(status_item, "isVisible")
                    else "n/a"
                )
                length = (
                    status_item.length() if hasattr(status_item, "length") else "n/a"
                )
                current_title = (
                    button.title()
                    if button is not None and hasattr(button, "title")
                    else status_item.title()
                )
                logger.info(
                    "ステータス反映確認: count=%s visible=%s length=%s title=%s",
                    self._status_refresh_count,
                    visible,
                    length,
                    current_title,
                )
        except Exception:
            logger.exception("ステータスアイテムの表示再反映に失敗しました")

    def _status_watchdog(self, _=None):
        """ステータスアイテムの見失いを監視し、必要なら再反映する。"""
        self._watchdog_tick_count += 1
        nsapp = getattr(self, "_nsapp", None)
        status_item = getattr(nsapp, "nsstatusitem", None) if nsapp is not None else None
        if status_item is None:
            logger.warning("ステータスアイテム参照を取得できません。再反映を試みます")
            self._force_status_item_refresh()
            return

        button = status_item.button() if hasattr(status_item, "button") else None
        visible = (
            status_item.isVisible()
            if hasattr(status_item, "isVisible")
            else True
        )
        button_has_content = True
        if button is not None and hasattr(button, "title") and hasattr(button, "image"):
            button_has_content = bool(button.title()) or bool(button.image())
        if self._watchdog_tick_count % 4 == 0:
            logger.info(
                "ステータス監視: visible=%s has_content=%s",
                visible,
                button_has_content,
            )

        if not visible or not button_has_content:
            logger.warning(
                "ステータス表示を再反映します (visible=%s, has_content=%s)",
                visible,
                button_has_content,
            )
            self._force_status_item_refresh()

    def _on_events_fetched(self, events: list[Event]):
        """予定取得完了時のコールバック（バックグラウンドスレッドから呼ばれる）

        UI 更新はメインスレッド (AppKit) で行う必要があるため、
        ここではデータを保持するだけで、_poll_pending_events が処理する。
        """
        with self._events_lock:
            self._pending_events = events

    def _poll_pending_events(self, _=None):
        """メインスレッドで保留中の予定更新を適用"""
        with self._events_lock:
            events = self._pending_events
            self._pending_events = None

        if events is None:
            return

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
        today_events = [e for e in events if e.start_time.date() == today]
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

        if not today_schedule or not today_schedule.timed_events:
            self.title = "* No Events"
            self._force_status_item_refresh()
            return

        # 開催中のイベントを探す
        current_event = None
        for ev in today_schedule.timed_events:
            if ev.start_time <= now < ev.end_time:
                current_event = ev
                break

        next_event = None
        for ev in today_schedule.timed_events:
            if ev.start_time > now:
                next_event = ev
                break

        if current_event and next_event:
            # 開催中 + 次の予定あり
            minutes_until = int(
                (next_event.start_time - now).total_seconds() / 60
            )
            time_str = next_event.start_time.strftime("%H:%M")
            remaining = self._format_remaining_compact(minutes_until)
            self.title = self._build_menubar_title(
                ">" + time_str, remaining
            )
        elif current_event:
            # 開催中で次の予定なし
            end_str = current_event.end_time.strftime("%H:%M")
            self.title = f">~{end_str}"
        elif next_event:
            minutes_until = int(
                (next_event.start_time - now).total_seconds() / 60
            )
            time_str = next_event.start_time.strftime("%H:%M")
            remaining = self._format_remaining_compact(minutes_until)
            self.title = self._build_menubar_title(time_str, remaining)
        else:
            self.title = "* All Done"

        self._force_status_item_refresh()

    def _format_remaining_compact(self, minutes: int) -> str:
        """トップバー向けに残り時間を短く表示する。"""
        if minutes < 0:
            return "live"
        if minutes == 0:
            return "soon"
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        rem = minutes % 60
        if rem == 0:
            return f"{hours}h"
        return f"{hours}h{rem}m"

    def _display_width(self, text: str) -> int:
        """メニューバー幅判定用の概算表示幅（全角=2, 半角=1）。"""
        width = 0
        for ch in text:
            width += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
        return width

    def _build_menubar_title(self, time_str: str, remaining: str) -> str:
        """幅に応じて段階的に短縮し、トップバーで消えにくいタイトルを返す。"""
        candidates = [
            f"{time_str}\u00b7{remaining}",
            f"{time_str}-{remaining}",
            time_str,
            "Cal",
        ]
        for candidate in candidates:
            if self._display_width(candidate) <= 12:
                return candidate
        return candidates[-1]

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
        self.title = "..."
        self._force_status_item_refresh()
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
        rumps.events.before_start.unregister(self._on_before_start)
        self.status_watchdog_timer.stop()
        self.title_timer.stop()
        self.fetch_timer.stop()
        self._poll_timer.stop()
        self.notifier.cancel_all()
        rumps.quit_application()
