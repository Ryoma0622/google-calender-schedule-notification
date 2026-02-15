import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Optional

from models import AppConfig, Event

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: AppConfig):
        self.config = config
        self._scheduled_timers: dict[str, threading.Timer] = {}
        self._meeting_open_timers: dict[str, threading.Timer] = {}
        self._notified_event_keys: set[str] = set()
        self._auto_opened_event_keys: set[str] = set()
        self._terminal_notifier_path = self._resolve_terminal_notifier_path()
        if self._terminal_notifier_path:
            logger.info(
                "通知バックエンド: terminal-notifier (%s)",
                self._terminal_notifier_path,
            )
        else:
            logger.warning(
                "terminal-notifier が見つからないため osascript フォールバックを使用します"
            )

    def _resolve_terminal_notifier_path(self) -> Optional[str]:
        """terminal-notifier の実行ファイルパスを解決する。"""
        candidates = [
            shutil.which("terminal-notifier"),
            "/opt/homebrew/bin/terminal-notifier",
            "/usr/local/bin/terminal-notifier",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            expanded = os.path.expanduser(candidate)
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded
        return None

    def _event_key(self, event: Event) -> str:
        """同一予定判定用キー"""
        return f"{event.title}_{event.start_time.isoformat()}"

    def schedule_notifications(self, events: list[Event]):
        """全予定に対して通知タイマーをセット"""
        self.cancel_all()
        now = datetime.now()
        active_event_keys = {
            self._event_key(event)
            for event in events
            if not event.is_all_day
        }
        self._notified_event_keys.intersection_update(active_event_keys)
        self._auto_opened_event_keys.intersection_update(active_event_keys)
        sent_immediately = 0
        auto_open_sent_immediately = 0
        auto_open_scheduled = 0
        auto_open_grace_period = timedelta(seconds=60)

        for event in events:
            if event.is_all_day:
                continue

            timer_key = self._event_key(event)
            if timer_key in self._notified_event_keys:
                continue

            if event.start_time <= now:
                continue

            notify_at = event.start_time - timedelta(
                minutes=self.config.notification_minutes_before
            )

            if notify_at <= now < event.start_time:
                # 通知時刻を過ぎていても、開始前なら即時通知して取りこぼしを防ぐ
                self._send_notification(event)
                self._notified_event_keys.add(timer_key)
                sent_immediately += 1
                continue

            delay = (notify_at - now).total_seconds()
            timer = threading.Timer(
                delay,
                self._send_notification_by_key,
                args=[timer_key, event],
            )
            timer.daemon = True
            timer.start()
            self._scheduled_timers[timer_key] = timer

        if self.config.auto_open_meeting_on_start:
            for event in events:
                if event.is_all_day or not event.meeting_url:
                    continue

                timer_key = self._event_key(event)
                if timer_key in self._auto_opened_event_keys:
                    continue

                if event.start_time <= now <= event.start_time + auto_open_grace_period:
                    self._open_meeting_by_key(timer_key, event)
                    auto_open_sent_immediately += 1
                    continue

                if event.start_time <= now:
                    continue

                delay = (event.start_time - now).total_seconds()
                open_timer = threading.Timer(
                    delay,
                    self._open_meeting_by_key,
                    args=[timer_key, event],
                )
                open_timer.daemon = True
                open_timer.start()
                self._meeting_open_timers[timer_key] = open_timer
                auto_open_scheduled += 1

        logger.info(
            "%d 件の通知をスケジュールしました (即時通知=%d, 自動起動=%d, 自動起動即時=%d)",
            len(self._scheduled_timers),
            sent_immediately,
            auto_open_scheduled,
            auto_open_sent_immediately,
        )

    def _send_notification_by_key(self, timer_key: str, event: Event):
        """タイマー経由の通知実行（送信済み管理付き）"""
        try:
            self._send_notification(event)
        finally:
            self._notified_event_keys.add(timer_key)
            self._scheduled_timers.pop(timer_key, None)

    def _open_meeting_by_key(self, timer_key: str, event: Event):
        """タイマー経由で会議 URL を自動起動（送信済み管理付き）"""
        try:
            if not event.meeting_url:
                return
            if datetime.now() >= event.end_time:
                logger.info("会議の自動起動をスキップ（終了時刻超過）: %s", event.title)
                return
            try:
                self._open_meeting_osascript(event.meeting_url)
                logger.info("会議を自動起動: %s", event.title)
            except Exception as e:
                logger.error("会議の自動起動に失敗: %s", e)
        finally:
            self._auto_opened_event_keys.add(timer_key)
            self._meeting_open_timers.pop(timer_key, None)

    def _send_notification(self, event: Event):
        """macOS 通知を送信"""
        title = f"\U0001f4c5 {event.start_time.strftime('%H:%M')} {event.title}"
        minutes = self.config.notification_minutes_before
        message = f"{minutes}分後に開始します"

        if event.meeting_url:
            message += "\nクリックして会議に参加"

        terminal_notifier = (
            self._terminal_notifier_path
            or self._resolve_terminal_notifier_path()
        )
        if terminal_notifier is None:
            logger.warning(
                "terminal-notifier が見つかりません。osascript にフォールバックします"
            )
            self._send_notification_osascript(event)
            return

        self._terminal_notifier_path = terminal_notifier

        # terminal-notifier を使用
        cmd = [
            terminal_notifier,
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
            # 参照先が消えていたら再解決してフォールバック
            self._terminal_notifier_path = self._resolve_terminal_notifier_path()
            logger.warning(
                "terminal-notifier 実行ファイルにアクセスできません。osascript にフォールバック"
            )
            self._send_notification_osascript(event)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"")
            stderr_text = (
                stderr.decode("utf-8", errors="ignore")[:200]
                if isinstance(stderr, bytes)
                else str(stderr)[:200]
            )
            logger.warning(f"terminal-notifier 通知送信エラー: {stderr_text or e}")
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
            subprocess.run(["osascript", "-e", script], capture_output=True, check=True)
            logger.info(f"通知送信(osascript): {event.title}")
        except Exception as e:
            logger.error(f"osascript 通知エラー: {e}")

    def _open_meeting_osascript(self, meeting_url: str):
        """osascript で会議 URL を開く。"""
        safe_url = meeting_url.replace('"', '\\"')
        script = f'open location "{safe_url}"'
        subprocess.run(["osascript", "-e", script], capture_output=True, check=True)

    def cancel_all(self):
        """全タイマーをキャンセル"""
        for timer in self._scheduled_timers.values():
            timer.cancel()
        self._scheduled_timers.clear()
        for timer in self._meeting_open_timers.values():
            timer.cancel()
        self._meeting_open_timers.clear()
