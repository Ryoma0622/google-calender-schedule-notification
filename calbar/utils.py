import re
import subprocess
import sys
from typing import Optional

MEETING_URL_PATTERNS = [
    # Google Meet
    r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}",
    # Zoom
    r"https://[\w.-]*zoom\.us/j/\d+(?:\?pwd=[\w]+)?",
    # Microsoft Teams
    r"https://teams\.microsoft\.com/l/meetup-join/[\w%.-]+",
    # Webex
    r"https://[\w.-]*\.webex\.com/[\w/.-]+",
]


def extract_meeting_url(text: str) -> Optional[str]:
    """テキストから最初にマッチした会議 URL を返す"""
    if not text:
        return None
    for pattern in MEETING_URL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def open_url(url: str):
    """URL をデフォルトブラウザで開く"""
    if sys.platform == "darwin":
        subprocess.run(["open", url])
    elif sys.platform == "linux":
        subprocess.run(["xdg-open", url])


def truncate_title(title: str, max_length: int) -> str:
    """タイトルを指定文字数で切り詰める"""
    if len(title) <= max_length:
        return title
    return title[:max_length] + "..."


def format_minutes_remaining(minutes: int) -> str:
    """残り時間を日本語で表示"""
    if minutes < 0:
        return "開始済み"
    if minutes == 0:
        return "まもなく"
    if minutes < 60:
        return f"{minutes}分後"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if remaining_minutes == 0:
        return f"{hours}時間後"
    return f"{hours}時間{remaining_minutes}分後"


WEEKDAY_NAMES_JA = ["月", "火", "水", "木", "金", "土", "日"]


def format_date_ja(d) -> str:
    """日付を日本語形式で整形 (例: 2026年2月14日（土）)"""
    weekday = WEEKDAY_NAMES_JA[d.weekday()]
    return f"{d.year}年{d.month}月{d.day}日（{weekday}）"
