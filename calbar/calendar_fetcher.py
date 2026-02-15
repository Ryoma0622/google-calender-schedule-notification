import asyncio
import logging
import os
import re
import subprocess
import unicodedata
from datetime import datetime, date, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page

# .app バンドル実行時にシステムの Playwright ブラウザを参照
# macOS / Linux それぞれの標準パスを順に探す
if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    _browser_candidates = [
        os.path.expanduser("~/Library/Caches/ms-playwright"),  # macOS
        os.path.expanduser("~/.cache/ms-playwright"),  # Linux
    ]
    for _candidate in _browser_candidates:
        if os.path.exists(_candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _candidate
            break
    else:
        # どちらも存在しない場合は macOS のデフォルトパスを設定
        # (playwright install 時にここに作成される)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browser_candidates[0]

from models import AppConfig, Event
from event_parser import parse_event_from_dom_data
from utils import extract_meeting_url

logger = logging.getLogger(__name__)

_chromium_checked = False


def _ensure_chromium_installed() -> None:
    """Chromium がインストール済みか確認し、未インストールなら自動取得する。

    .app バンドルから配布した場合、ユーザー環境に Playwright の Chromium が
    存在しないため、初回起動時に自動インストールを行う。
    """
    global _chromium_checked
    if _chromium_checked:
        return

    from playwright._impl._driver import compute_driver_executable

    node_path, cli_path = compute_driver_executable()
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")

    # ブラウザディレクトリに chromium- で始まるフォルダがあればインストール済み
    if browsers_path and os.path.isdir(browsers_path):
        for entry in os.listdir(browsers_path):
            if entry.startswith("chromium-"):
                _chromium_checked = True
                return

    logger.info("Chromium が見つかりません。自動インストールを開始します...")
    try:
        env = os.environ.copy()
        if browsers_path:
            env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
        result = subprocess.run(
            [node_path, cli_path, "install", "chromium"],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("Chromium のインストールが完了しました")
        else:
            logger.error(
                "Chromium のインストールに失敗しました: %s", result.stderr[:500]
            )
    except Exception as e:
        logger.error("Chromium の自動インストール中にエラー: %s", e)

    _chromium_checked = True


CALENDAR_URL = "https://calendar.google.com"
WEEK_VIEW_URLS = [
    # 複数アカウント利用時に /r/week だと空カレンダーを開く場合があるため、
    # まず primary account (/u/0) を優先する。
    "https://calendar.google.com/calendar/u/0/r/week",
    "https://calendar.google.com/calendar/r/week",
]
# Google Calendar へのアクセスを前提とした認証 URL
# 未認証時に calendar.google.com を開くと商品紹介ページにリダイレクトされるため、
# accounts.google.com 経由で認証後に Calendar へ遷移させる
AUTH_URL = (
    "https://accounts.google.com/ServiceLogin"
    "?continue=https://calendar.google.com/calendar/u/0/r/week"
)

TIME_RANGE_PATTERN = re.compile(
    r"(?P<start>"
    r"(?:(?:午前|午後)\s*)?\d{1,2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm))?"
    r"|(?:(?:午前|午後)\s*)?\d{1,2}時(?:\d{1,2}分?)?"
    r")"
    r"\s*[–—-～〜]\s*"
    r"(?P<end>"
    r"(?:(?:午前|午後)\s*)?\d{1,2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm))?"
    r"|(?:(?:午前|午後)\s*)?\d{1,2}時(?:\d{1,2}分?)?"
    r")"
)

WEEKDAY_TOKENS = {
    "月",
    "火",
    "水",
    "木",
    "金",
    "土",
    "日",
    "月曜日",
    "火曜日",
    "水曜日",
    "木曜日",
    "金曜日",
    "土曜日",
    "日曜日",
}
NON_CALENDAR_TOKENS = {
    "場所の指定なし",
    "場所なし",
    "no location",
    "location",
    "場所",
    "予定",
    "event",
}
NORMALIZED_NON_CALENDAR_TOKENS = {
    re.sub(r"\s+", "", unicodedata.normalize("NFKC", token).strip().lower())
    for token in NON_CALENDAR_TOKENS
}
ACCOUNT_LABEL_SELECTORS = [
    'a[aria-label*="Google アカウント"]',
    'button[aria-label*="Google アカウント"]',
    '[aria-label*="Google アカウント"]',
    'a[aria-label*="Google Account"]',
    'button[aria-label*="Google Account"]',
    '[aria-label*="Google Account"]',
]
TimedEventRecord = tuple[Event, Optional[str], str]


def _remove_singleton_lock(profile_path: str) -> None:
    """Chrome の SingletonLock を削除する。

    persistent context を使う場合、Chrome が正常終了しないと
    SingletonLock が残り次回起動が失敗するため、起動前に削除する。
    """
    lock = os.path.join(profile_path, "SingletonLock")
    try:
        os.remove(lock)
    except FileNotFoundError:
        pass


async def is_authenticated(page: Page) -> bool:
    """Google Calendar のメインビューが表示されているか判定"""
    try:
        await page.wait_for_selector('[data-view-heading]', timeout=5000)
        return True
    except Exception:
        return False


async def authenticate(config: AppConfig):
    """未認証時にヘッド付きブラウザを起動しユーザーに手動ログインさせる"""
    _ensure_chromium_installed()
    profile_path = os.path.expanduser(config.browser_profile_path)
    os.makedirs(profile_path, exist_ok=True)
    _remove_singleton_lock(profile_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=[
                "--window-size=800,600",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(AUTH_URL)

        logger.info("ブラウザでGoogleアカウントにログインしてください...")

        # ユーザーが手動でログインするのを最大5分待つ
        try:
            await page.wait_for_selector('[data-view-heading]', timeout=300000)
            logger.info("認証が完了しました")
        except Exception:
            logger.warning("認証がタイムアウトしました")

        await browser.close()


async def _extract_week_dates(page: Page) -> list[date]:
    """Week ビューのヘッダーから各日の日付を抽出"""
    dates = []
    # カラムヘッダーから日付を取得
    headers = await page.query_selector_all('[data-datekey]')
    for header in headers:
        datekey = await header.get_attribute('data-datekey')
        if datekey:
            try:
                # datekey 形式: "2026214" (YYYYMD) or "20260214" (YYYYMMDD)
                # Google Calendar は YYYYMMDD 形式を使用
                d = datetime.strptime(datekey, "%Y%m%d").date()
                dates.append(d)
            except ValueError:
                continue

    if not dates:
        # フォールバック: 今日を基準に1週間分を生成
        today = date.today()
        # 週の開始日（月曜日）を計算
        start = today - timedelta(days=today.weekday())
        dates = [start + timedelta(days=i) for i in range(7)]

    return sorted(dates)


async def _open_best_week_view(page: Page) -> str:
    """週ビュー URL を順に試し、イベント要素を検出できる URL を選ぶ。"""
    selected_url = WEEK_VIEW_URLS[0]
    selected_count = -1

    for url in WEEK_VIEW_URLS:
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector('[data-eventid]', timeout=5000)
        except Exception:
            # イベントがない週でもタイムアウトはあり得る
            pass
        await page.wait_for_timeout(500)

        if not await is_authenticated(page):
            continue

        count = await page.locator('[data-eventid]').count()
        logger.info("週ビュー候補: %s (data-eventid=%d)", url, count)

        if count > selected_count:
            selected_url = url
            selected_count = count

        if count > 0:
            return url

    # 最有力 URL を再度開いてから呼び出し元へ返す
    if page.url != selected_url:
        await page.goto(selected_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

    return selected_url


async def _extract_all_day_events(page: Page, week_dates: list[date]) -> list[Event]:
    """終日イベント領域から終日予定を抽出"""
    events = []

    # 終日イベントを探す - aria-label を使用
    all_day_chips = await page.query_selector_all(
        '[data-eventid][data-allday="true"], '
        '[aria-label][role="button"][data-eventchip]'
    )

    for chip in all_day_chips:
        aria_label = await chip.get_attribute('aria-label') or ''
        # 終日イベントかどうかを判定
        # aria-label に日付情報が含まれることが多い
        if not aria_label:
            text_content = await chip.text_content() or ''
            aria_label = text_content

        if aria_label:
            quoted_title = re.search(r"「([^」]+)」", aria_label)
            title = quoted_title.group(1).strip() if quoted_title else aria_label.strip()
            # タイトルから時刻情報がなければ終日イベントと判定
            if not _extract_time_info(aria_label):
                calendar_name = _extract_calendar_name_from_label(aria_label, title)
                for d in week_dates:
                    events.append(parse_event_from_dom_data(
                        title=title,
                        time_info="",
                        event_date=d,
                        calendar_name=calendar_name or "",
                        is_all_day=True,
                    ))
                break  # 重複防止

    return events


async def _extract_timed_events(
    page: Page,
    week_dates: list[date],
) -> list[TimedEventRecord]:
    """時間指定イベントを抽出（Event と識別情報の組を返す）"""
    event_pairs: list[TimedEventRecord] = []

    # イベントチップを取得 - aria-label と role 属性を使用
    event_elements = await page.query_selector_all(
        '[data-eventid]:not([data-allday="true"]), '
        '[role="button"][data-eventchip]'
    )

    processed_labels = set()

    parse_failed_labels: list[str] = []

    for element in event_elements:
        label = await element.get_attribute('aria-label') or ''
        if not label:
            label = await element.text_content() or ''

        label = label.strip()
        if not label or label in processed_labels:
            continue
        processed_labels.add(label)

        # aria-label パターン: "イベントタイトル, 2月14日 金曜日, 9:00～10:00"
        # または: "9:00 - 10:00, イベントタイトル"
        event_data = _parse_aria_label(label, week_dates)
        if event_data:
            event_id = await element.get_attribute('data-eventid')
            if not event_id:
                inner = await element.query_selector('[data-eventid]')
                if inner:
                    event_id = await inner.get_attribute('data-eventid')
            event_pairs.append((event_data, event_id, label))
        elif len(parse_failed_labels) < 3:
            parse_failed_labels.append(label[:200])

    if not event_pairs and parse_failed_labels:
        logger.warning(
            "時間指定イベントの解析に失敗しました。ラベル例: %s",
            " | ".join(parse_failed_labels),
        )

    return event_pairs


def _parse_aria_label(label: str, week_dates: list[date]) -> Optional[Event]:
    """aria-label テキストからイベント情報をパース"""
    time_info = _extract_time_info(label)
    if not time_info:
        return None

    time_span = _extract_time_span(label)

    # タイトル抽出: 「...」があれば最優先
    quoted_title = re.search(r"「([^」]+)」", label)
    if quoted_title:
        title = quoted_title.group(1).strip()
    else:
        title = label
        # 時刻部分を除去
        if time_span:
            start, end = time_span
            title = (title[:start] + " " + title[end:]).strip()
        # 日付部分を除去（例: "2026年 2月 15日", "2月14日 金曜日"）
        title = re.sub(r"\d{4}年\s*\d{1,2}月\s*\d{1,2}日", " ", title)
        title = re.sub(r"\d{1,2}月\s*\d{1,2}日\s*[月火水木金土日]曜日?", " ", title)
        # カレンダー補助文言を除去
        title = re.sub(r"(場所の指定なし|No location)", " ", title, flags=re.IGNORECASE)
        # カンマや余分な空白を除去
        title = re.sub(r"[,、]\s*", " ", title).strip()
        title = re.sub(r"\s+", " ", title).strip()

    if not title:
        title = "（タイトルなし）"

    # 日付を推定
    event_date = _extract_date_from_label(label, week_dates)
    calendar_name = _extract_calendar_name_from_label(label, title)

    return parse_event_from_dom_data(
        title=title,
        time_info=time_info,
        event_date=event_date,
        calendar_name=calendar_name or "",
    )


def _split_label_tokens(text: str) -> list[str]:
    return [token.strip() for token in re.split(r"[、,]", text) if token.strip()]


def _normalize_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.removesuffix("さん")
    normalized = normalized.removesuffix("様")
    return normalized


def _clean_label_token(token: str) -> str:
    cleaned = token.strip().strip("「」\"'[]()（）")
    cleaned = re.sub(r"^(?:カレンダー|calendar)[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _looks_like_calendar_name(token: str, title: str) -> bool:
    if not token:
        return False
    if token in WEEKDAY_TOKENS:
        return False
    if _extract_time_info(token):
        return False
    if re.search(r"\d{4}年\s*\d{1,2}月\s*\d{1,2}日", token):
        return False
    if re.search(r"\d{1,2}月\s*\d{1,2}日", token):
        return False
    if _normalize_identity(token) == _normalize_identity(title):
        return False
    if _normalize_identity(token) in NORMALIZED_NON_CALENDAR_TOKENS:
        return False
    return True


def _extract_calendar_name_from_label(label: str, title: str) -> Optional[str]:
    candidates: list[str] = []

    quoted_title_span = re.search(r"「[^」]+」", label)
    if quoted_title_span:
        candidates.extend(_split_label_tokens(label[quoted_title_span.end():]))
    else:
        tokens = _split_label_tokens(label)
        title_norm = _normalize_identity(title)
        title_index = -1
        for i, token in enumerate(tokens):
            if _normalize_identity(_clean_label_token(token)) == title_norm:
                title_index = i
                break
        if title_index >= 0:
            candidates.extend(tokens[title_index + 1:])
        else:
            candidates.extend(tokens)

    for candidate in candidates:
        cleaned = _clean_label_token(candidate)
        if _looks_like_calendar_name(cleaned, title):
            return cleaned
    return None


def _extract_aliases_from_account_label(label: str) -> tuple[Optional[str], set[str]]:
    display_name: Optional[str] = None
    aliases: set[str] = set()

    name_match = re.search(
        r"Google(?:\s*アカウント|\s*Account)[:：]\s*([^\(（,、]+)",
        label,
        flags=re.IGNORECASE,
    )
    if name_match:
        display_name = name_match.group(1).strip()
        normalized = _normalize_identity(display_name)
        if normalized:
            aliases.add(normalized)

    email_match = re.search(
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        label,
    )
    if email_match:
        email = email_match.group(1).strip()
        normalized_email = _normalize_identity(email)
        if normalized_email:
            aliases.add(normalized_email)
            aliases.add(normalized_email.split("@", 1)[0])
        if display_name is None:
            display_name = email

    return display_name, aliases


async def _extract_own_calendar_aliases(page: Page) -> tuple[Optional[str], set[str]]:
    seen_labels: set[str] = set()
    for selector in ACCOUNT_LABEL_SELECTORS:
        elements = await page.query_selector_all(selector)
        for element in elements[:5]:
            label = (await element.get_attribute("aria-label") or "").strip()
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            display_name, aliases = _extract_aliases_from_account_label(label)
            if aliases:
                return display_name, aliases
    return None, set()


def _is_own_calendar_event(event: Event, own_aliases: set[str]) -> bool:
    calendar_name = (event.calendar_name or "").strip()
    if not calendar_name:
        # カレンダー名を取れないケースは誤除外を避けて残す
        return True

    normalized_calendar = _normalize_identity(calendar_name)
    if not normalized_calendar:
        return True

    if normalized_calendar in own_aliases:
        return True

    for alias in own_aliases:
        if normalized_calendar.startswith(alias + "（") or normalized_calendar.startswith(alias + "("):
            return True

    return False


def _extract_time_span(label: str) -> Optional[tuple[int, int]]:
    """ラベル内の時刻範囲の位置を返す。"""
    match = TIME_RANGE_PATTERN.search(label)
    if not match:
        return None
    return match.span()


def _extract_time_info(label: str) -> Optional[str]:
    """ラベルから時刻範囲を HH:MM - HH:MM 形式で返す。"""
    match = TIME_RANGE_PATTERN.search(label)
    if not match:
        return None

    start_raw = match.group("start")
    end_raw = match.group("end")

    start_norm, start_meridiem = _normalize_time_token(start_raw)
    if not start_norm:
        return None

    end_norm, _ = _normalize_time_token(end_raw, fallback_meridiem=start_meridiem)
    if not end_norm:
        return None

    return f"{start_norm} - {end_norm}"


def _normalize_time_token(
    token: str,
    fallback_meridiem: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """時刻トークンを 24 時間の HH:MM に正規化する。"""
    value = token.strip()
    meridiem: Optional[str] = None

    # 日本語 AM/PM（前置）
    m = re.match(r"^(午前|午後)\s*", value)
    if m:
        meridiem = m.group(1)
        value = value[m.end():].strip()

    # 英語 AM/PM（後置）
    m = re.search(r"\s*(AM|PM|am|pm)$", value)
    if m:
        meridiem = m.group(1).lower()
        value = value[:m.start()].strip()

    if meridiem is None:
        meridiem = fallback_meridiem

    hour: Optional[int] = None
    minute = 0

    # 24時間/12時間 (HH:MM)
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?$", value)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
    else:
        # 日本語 (H時 / H時M分)
        m = re.match(r"^(\d{1,2})時(?:\s*(\d{1,2})分?)?$", value)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)

    if hour is None or minute > 59:
        return None, meridiem

    # 12時間表記を24時間に正規化
    if meridiem in {"午前", "午後", "am", "pm"} and 0 <= hour <= 12:
        hour = hour % 12
        if meridiem in {"午後", "pm"}:
            hour += 12

    if hour > 23:
        return None, meridiem

    return f"{hour:02d}:{minute:02d}", meridiem


def _extract_date_from_label(label: str, week_dates: list[date]) -> date:
    """aria-label から日付を抽出"""
    # "2026年 2月 14日" パターン
    ymd_match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", label)
    if ymd_match:
        year = int(ymd_match.group(1))
        month = int(ymd_match.group(2))
        day = int(ymd_match.group(3))
        candidate = date(year, month, day)
        if candidate in week_dates:
            return candidate
        return candidate

    # "2月14日" / "2月 14日" パターン
    date_match = re.search(r'(\d{1,2})月\s*(\d{1,2})日', label)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        today = date.today()
        # 年を推定
        candidate = date(today.year, month, day)
        if candidate in week_dates:
            return candidate
        return candidate

    # 曜日パターン
    weekday_map = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
    for name, wd in weekday_map.items():
        if f"{name}曜" in label:
            for d in week_dates:
                if d.weekday() == wd:
                    return d

    # フォールバック: 今日
    return date.today()


async def _extract_meeting_url_from_chip(element) -> Optional[str]:
    """イベントチップ内の属性/リンクから会議 URL を抽出"""
    aria_label = await element.get_attribute('aria-label') or ''
    url = extract_meeting_url(aria_label)
    if url:
        return url

    href = await element.get_attribute('href') or ''
    url = extract_meeting_url(href)
    if url:
        return url

    links = await element.query_selector_all('a[href], [href]')
    for link in links:
        href = await link.get_attribute('href') or ''
        url = extract_meeting_url(href)
        if url:
            return url

    return None


async def _find_timed_event_element(
    page: Page,
    event_id: Optional[str],
    label: str,
) -> Optional[object]:
    """詳細取得対象のイベント要素を再解決する（stale handle 対策）"""
    event_elements = await page.query_selector_all(
        '[data-eventid]:not([data-allday="true"]), '
        '[role="button"][data-eventchip]'
    )

    normalized_label = label.strip()
    fallback = None

    for element in event_elements:
        current_event_id = (await element.get_attribute('data-eventid') or '').strip()
        if not current_event_id:
            inner = await element.query_selector('[data-eventid]')
            if inner:
                current_event_id = (await inner.get_attribute('data-eventid') or '').strip()

        if event_id and current_event_id and current_event_id == event_id:
            return element

        if fallback is None and normalized_label:
            current_label = (await element.get_attribute('aria-label') or '').strip()
            if not current_label:
                current_label = (await element.text_content() or '').strip()
            if current_label == normalized_label:
                fallback = element

    return fallback


async def _get_event_detail(page: Page, element, event: Event) -> Event:
    """イベントをクリックして詳細情報を取得"""
    async def _get_visible_detail_panel():
        panels = await page.query_selector_all(
            '[role="dialog"], [data-eventdetails], .ecHOqf'
        )
        for panel in panels:
            try:
                if await panel.is_visible():
                    return panel
            except Exception:
                continue
        return None

    async def _open_detail_panel_by_click(target) -> Optional[object]:
        try:
            await target.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass

        for _ in range(2):
            try:
                await target.click(timeout=1200, force=True)
            except Exception:
                continue
            await page.wait_for_timeout(250)
            panel = await _get_visible_detail_panel()
            if panel:
                return panel
        return None

    try:
        # チップ自体に会議リンクが埋まっている場合はクリック不要
        chip_url = await _extract_meeting_url_from_chip(element)
        if chip_url:
            event.meeting_url = chip_url
            return event

        # クリック対象を複数試して、詳細パネルを開く
        targets = [element]
        inner = await element.query_selector('.leOeGd[data-eventid]')
        if inner:
            targets.insert(0, inner)

        detail_panel = None
        for target in targets:
            detail_panel = await _open_detail_panel_by_click(target)
            if detail_panel:
                break

        if detail_panel:
            detail_text = await detail_panel.text_content() or ''

            # 会議 URL を抽出
            meeting_url = extract_meeting_url(detail_text)
            if meeting_url:
                event.meeting_url = meeting_url

            # リンク要素から URL も探す
            links = await detail_panel.query_selector_all('a[href]')
            for link in links:
                href = await link.get_attribute('href') or ''
                url = extract_meeting_url(href)
                if url:
                    event.meeting_url = url
                    break

            # 場所の取得
            location_el = await detail_panel.query_selector(
                '[data-location], [aria-label*="場所"], [aria-label*="location"]'
            )
            if location_el:
                event.location = await location_el.text_content()

        # 閉じるボタンは可視性待ちで詰まりやすいので Escape を優先する
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass
        await page.wait_for_timeout(150)

    except Exception as e:
        logger.debug(f"詳細取得失敗: {e}")
        # Escape で閉じる試行
        try:
            await page.keyboard.press('Escape')
        except Exception:
            pass

    return event


async def fetch_events(config: AppConfig) -> list[Event]:
    """1 週間分の予定を取得"""
    _ensure_chromium_installed()
    profile_path = os.path.expanduser(config.browser_profile_path)
    os.makedirs(profile_path, exist_ok=True)
    _remove_singleton_lock(profile_path)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            await page.goto(WEEK_VIEW_URLS[0], wait_until="domcontentloaded")

            if not await is_authenticated(page):
                await browser.close()
                logger.info("認証が必要です。ブラウザを起動します...")
                await authenticate(config)
                # 認証後にリトライ
                return await fetch_events(config)

            selected_url = await _open_best_week_view(page)
            logger.info("週ビューURLを選択: %s", selected_url)

            # ページの読み込みを待つ
            await page.wait_for_timeout(2000)

            events: list[Event] = []
            all_day_events: list[Event] = []
            timed_event_pairs: list[TimedEventRecord] = []
            last_data_eventid_count = 0
            own_calendar_display_name: Optional[str] = None
            own_calendar_aliases: set[str] = set()

            if config.show_only_own_calendar:
                own_calendar_display_name, own_calendar_aliases = await _extract_own_calendar_aliases(page)
                if own_calendar_aliases:
                    logger.info(
                        "自分のカレンダー限定フィルタを有効化: %s",
                        own_calendar_display_name or "アカウント名未取得",
                    )
                else:
                    logger.warning(
                        "自分のカレンダー名を取得できなかったため、限定フィルタをスキップします"
                    )

            # Google Calendar は描画が遅れることがあるため、0件時は再試行する
            for attempt in range(1, 4):
                # 週の日付を取得
                week_dates = await _extract_week_dates(page)
                events = []
                all_day_events = []
                timed_events: list[Event] = []
                parsed_event_count = 0

                # 終日イベントの取得
                try:
                    all_day_events = await _extract_all_day_events(page, week_dates)
                except Exception as e:
                    logger.warning(f"終日イベント取得失敗: {e}")
                    all_day_events = []

                # 時間指定イベントの取得
                try:
                    timed_event_pairs = await _extract_timed_events(page, week_dates)
                    timed_events = [event for event, _, _ in timed_event_pairs]
                except Exception as e:
                    logger.warning(f"時間指定イベント取得失敗: {e}")
                    timed_events = []
                    timed_event_pairs = []

                timed_event_count_raw = len(timed_events)
                parsed_event_count = len(all_day_events) + len(timed_events)

                if config.show_only_own_calendar and own_calendar_aliases:
                    before_filter_count = parsed_event_count
                    all_day_events = [
                        event
                        for event in all_day_events
                        if _is_own_calendar_event(event, own_calendar_aliases)
                    ]
                    timed_event_pairs = [
                        (event, event_id, label)
                        for event, event_id, label in timed_event_pairs
                        if _is_own_calendar_event(event, own_calendar_aliases)
                    ]
                    timed_events = [event for event, _, _ in timed_event_pairs]
                    after_filter_count = len(all_day_events) + len(timed_events)
                    if before_filter_count != after_filter_count:
                        logger.info(
                            "自分のカレンダー限定で %d 件を除外しました (attempt=%d)",
                            before_filter_count - after_filter_count,
                            attempt,
                        )

                events.extend(all_day_events)
                events.extend(timed_events)

                last_data_eventid_count = await page.locator('[data-eventid]').count()
                logger.info(
                    "時間指定イベント解析: %d 件 (data-eventid=%d, attempt=%d)",
                    timed_event_count_raw,
                    last_data_eventid_count,
                    attempt,
                )

                if parsed_event_count > 0:
                    break

                if attempt < 3:
                    logger.warning(
                        "予定を0件検出。週ビューを再読み込みして再試行します (attempt=%d)",
                        attempt,
                    )
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

            if not events and config.show_only_own_calendar and own_calendar_aliases:
                logger.info("自分のカレンダーに該当する予定はありませんでした")
            elif not events:
                logger.warning(
                    "再試行後も0件でした (data-eventid=%d)。",
                    last_data_eventid_count,
                )

            # 各イベントの詳細を取得（会議URL等）
            all_day_count = len([e for e in events if e.is_all_day])
            for i in range(len(timed_event_pairs)):
                event_index = all_day_count + i
                _, event_id, label = timed_event_pairs[i]
                element = await _find_timed_event_element(page, event_id, label)
                if element is None:
                    logger.debug(
                        "詳細取得対象を再解決できませんでした (timed_index=%d, event_id=%s)",
                        i,
                        event_id or "unknown",
                    )
                    continue
                try:
                    events[event_index] = await _get_event_detail(
                        page,
                        element,
                        events[event_index],
                    )
                except Exception as e:
                    logger.debug(
                        f"詳細取得タイムアウト/失敗 (timed_index={i}, event_index={event_index}): {e}"
                    )

            logger.info(f"{len(events)} 件の予定を取得しました")
            return events

        except Exception as e:
            logger.error(f"予定取得エラー: {e}")
            raise
        finally:
            await browser.close()


def fetch_events_sync(config: AppConfig) -> list[Event]:
    """同期版の予定取得関数（スレッドから呼び出し用）"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(fetch_events(config))
    finally:
        loop.close()
