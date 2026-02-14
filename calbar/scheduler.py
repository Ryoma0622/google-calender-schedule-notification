import json
import logging
import os
import threading
from datetime import datetime
from typing import Callable, Optional

from models import AppConfig, Event
from calendar_fetcher import fetch_events_sync

logger = logging.getLogger(__name__)


class FetchScheduler:
    def __init__(self, config: AppConfig, on_events_updated: Callable[[list[Event]], None]):
        self.config = config
        self.on_events_updated = on_events_updated

    def run_fetch(self):
        """バックグラウンドスレッドで Playwright 取得を実行"""
        thread = threading.Thread(target=self._fetch_thread, daemon=True)
        thread.start()

    def _fetch_thread(self):
        try:
            events = fetch_events_sync(self.config)
            self._cache_events(events)
            self.on_events_updated(events)
        except Exception as e:
            logger.error(f"予定取得エラー: {e}")
            # ネットワークエラー等 → キャッシュから読み込み
            cached = self._load_cache()
            if cached:
                self.on_events_updated(cached)
            else:
                logger.warning("キャッシュデータがありません")

    def _cache_events(self, events: list[Event]):
        """取得結果を JSON キャッシュに保存"""
        cache_path = os.path.expanduser(self.config.cache_path)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        data = [
            {
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "is_all_day": e.is_all_day,
                "location": e.location,
                "meeting_url": e.meeting_url,
                "description": e.description,
                "calendar_name": e.calendar_name,
            }
            for e in events
        ]
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"キャッシュ保存: {len(events)} 件")
        except Exception as e:
            logger.error(f"キャッシュ保存エラー: {e}")

    def _load_cache(self) -> Optional[list[Event]]:
        """キャッシュから予定を読み込み"""
        cache_path = os.path.expanduser(self.config.cache_path)
        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)

            events = []
            for item in data:
                events.append(
                    Event(
                        title=item["title"],
                        start_time=datetime.fromisoformat(item["start_time"]),
                        end_time=datetime.fromisoformat(item["end_time"]),
                        is_all_day=item.get("is_all_day", False),
                        location=item.get("location"),
                        meeting_url=item.get("meeting_url"),
                        description=item.get("description"),
                        calendar_name=item.get("calendar_name"),
                    )
                )
            logger.info(f"キャッシュから {len(events)} 件の予定を読み込みました")
            return events
        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {e}")
            return None
