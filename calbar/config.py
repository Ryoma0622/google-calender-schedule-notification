import json
import os

from models import AppConfig

CONFIG_DIR = os.path.expanduser("~/.calbar")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "notification_minutes_before": 5,
    "fetch_interval_minutes": 5,
    "show_all_day_events": True,
    "show_only_own_calendar": True,
    "auto_open_meeting_on_start": False,
    "max_title_length_menubar": 30,
}


def load_config() -> AppConfig:
    """設定ファイルを読み込み、AppConfig を返す"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = {**DEFAULT_CONFIG, **json.load(f)}
            return AppConfig(**data)
    return AppConfig(**DEFAULT_CONFIG)


def save_config(config: AppConfig):
    """AppConfig を JSON ファイルに保存"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "notification_minutes_before": config.notification_minutes_before,
                "fetch_interval_minutes": config.fetch_interval_minutes,
                "show_all_day_events": config.show_all_day_events,
                "show_only_own_calendar": config.show_only_own_calendar,
                "auto_open_meeting_on_start": config.auto_open_meeting_on_start,
                "max_title_length_menubar": config.max_title_length_menubar,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
