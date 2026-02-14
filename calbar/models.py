from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class Event:
    title: str
    start_time: datetime  # 終日予定の場合は当日 00:00:00
    end_time: datetime  # 終日予定の場合は翌日 00:00:00
    is_all_day: bool = False
    location: Optional[str] = None
    meeting_url: Optional[str] = None  # Google Meet / Zoom / Teams URL
    description: Optional[str] = None
    calendar_name: Optional[str] = None


@dataclass
class DaySchedule:
    date: date
    events: list[Event] = field(default_factory=list)

    @property
    def all_day_events(self) -> list[Event]:
        return [e for e in self.events if e.is_all_day]

    @property
    def timed_events(self) -> list[Event]:
        return sorted(
            [e for e in self.events if not e.is_all_day],
            key=lambda e: e.start_time,
        )


@dataclass
class AppConfig:
    notification_minutes_before: int = 5  # 通知タイミング（分前）
    fetch_interval_minutes: int = 5  # 自動取得間隔
    browser_profile_path: str = "~/.calbar/browser_profile"
    cache_path: str = "~/.calbar/cache.json"
    config_path: str = "~/.calbar/config.json"
    show_all_day_events: bool = True
    show_only_own_calendar: bool = True
    max_title_length_menubar: int = 30  # メニューバー表示のタイトル文字数上限
