import re
from datetime import datetime, date, timedelta
from typing import Optional

from models import Event
from utils import extract_meeting_url


def parse_time_string(time_str: str, reference_date: date) -> Optional[datetime]:
    """時刻文字列をパースして datetime を返す

    対応フォーマット:
      - "9:00" / "09:00" / "9:00 AM" / "9:00 PM"
      - "14:00" (24時間)
    """
    time_str = time_str.strip()

    # AM/PM 形式
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            t = datetime.strptime(time_str, fmt).time()
            return datetime.combine(reference_date, t)
        except ValueError:
            continue

    # 24時間形式
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            t = datetime.strptime(time_str, fmt).time()
            return datetime.combine(reference_date, t)
        except ValueError:
            continue

    return None


def parse_time_range(time_range_str: str, reference_date: date) -> tuple[Optional[datetime], Optional[datetime]]:
    """時間範囲文字列をパースして (start, end) を返す

    対応フォーマット:
      - "9:00 - 10:00"
      - "9:00 AM - 10:00 AM"
      - "9 AM - 10 AM"
      - "9:00\u2013 10:00" (en dash)
    """
    # 区切り文字で分割（ハイフン、en-dash、em-dash）
    parts = re.split(r"\s*[–—-]\s*", time_range_str, maxsplit=1)
    if len(parts) != 2:
        return None, None

    start = parse_time_string(parts[0], reference_date)
    end = parse_time_string(parts[1], reference_date)
    return start, end


def parse_event_from_dom_data(
    title: str,
    time_info: str,
    event_date: date,
    detail_text: str = "",
    location: str = "",
    calendar_name: str = "",
    is_all_day: bool = False,
) -> Event:
    """DOM から取得した生データを Event オブジェクトに変換"""
    start_time = datetime.combine(event_date, datetime.min.time())
    end_time = datetime.combine(event_date + timedelta(days=1), datetime.min.time())

    if not is_all_day and time_info:
        parsed_start, parsed_end = parse_time_range(time_info, event_date)
        if parsed_start:
            start_time = parsed_start
        if parsed_end:
            end_time = parsed_end
        elif parsed_start:
            # 終了時刻がなければ開始から1時間後
            end_time = parsed_start + timedelta(hours=1)

    meeting_url = extract_meeting_url(detail_text) or extract_meeting_url(location)

    return Event(
        title=title.strip(),
        start_time=start_time,
        end_time=end_time,
        is_all_day=is_all_day,
        location=location.strip() if location else None,
        meeting_url=meeting_url,
        description=detail_text.strip() if detail_text else None,
        calendar_name=calendar_name.strip() if calendar_name else None,
    )
