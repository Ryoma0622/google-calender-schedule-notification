import logging
import subprocess
import threading
from datetime import datetime, timedelta

from models import AppConfig, Event
from utils import open_url

logger = logging.getLogger(__name__)


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

        logger.info(f"{len(self._scheduled_timers)} 件の通知をスケジュールしました")

    def _send_notification(self, event: Event):
        """macOS 通知を送信"""
        title = f"\U0001f4c5 {event.start_time.strftime('%H:%M')} {event.title}"
        minutes = self.config.notification_minutes_before
        message = f"{minutes}分後に開始します"

        if event.meeting_url:
            message += "\nクリックして会議に参加"

        # terminal-notifier を使用（Homebrew でインストール）
        cmd = [
            "terminal-notifier",
            "-title",
            title,
            "-message",
            message,
            "-sound",
            "default",
            "-group",
            f"calbar-{event.start_time.isoformat()}",
        ]

        if event.meeting_url:
            cmd.extend(["-open", event.meeting_url])

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"通知送信: {event.title}")
        except FileNotFoundError:
            # terminal-notifier がない場合、osascript フォールバック
            logger.debug("terminal-notifier が見つかりません。osascript にフォールバック")
            self._send_notification_osascript(event)
        except subprocess.CalledProcessError as e:
            logger.warning(f"通知送信エラー: {e}")
            self._send_notification_osascript(event)

    def _send_notification_osascript(self, event: Event):
        """osascript によるフォールバック通知"""
        title = f"{event.start_time.strftime('%H:%M')} {event.title}"
        minutes = self.config.notification_minutes_before
        message = f"{minutes}分後に開始します"

        # osascript 内の特殊文字をエスケープ
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')

        script = (
            f'display notification "{safe_message}" '
            f'with title "{safe_title}" sound name "default"'
        )

        try:
            subprocess.run(["osascript", "-e", script], capture_output=True)
        except Exception as e:
            logger.error(f"osascript 通知エラー: {e}")

        # 会議 URL がある場合は自動で開く
        if event.meeting_url:
            open_url(event.meeting_url)

    def cancel_all(self):
        """全タイマーをキャンセル"""
        for timer in self._scheduled_timers.values():
            timer.cancel()
        self._scheduled_timers.clear()
