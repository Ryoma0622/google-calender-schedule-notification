import asyncio
import logging
import os
import re
from datetime import datetime, date, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext

from models import AppConfig, Event
from event_parser import parse_event_from_dom_data
from utils import extract_meeting_url

logger = logging.getLogger(__name__)

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
            # 終日イベントの場合
            title = aria_label.strip()
            # タイトルから時刻情報がなければ終日イベントと判定
            time_pattern = re.compile(r'\d{1,2}:\d{2}')
            if not time_pattern.search(title):
                for d in week_dates:
                    events.append(parse_event_from_dom_data(
                        title=title,
                        time_info="",
                        event_date=d,
                        is_all_day=True,
                    ))
                break  # 重複防止

    return events


async def _extract_timed_events(
    page: Page,
    week_dates: list[date],
) -> list[tuple[Event, object]]:
    """時間指定イベントを抽出（Event と対応する要素の組を返す）"""
    event_pairs: list[tuple[Event, object]] = []

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
            event_pairs.append((event_data, element))
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

    return parse_event_from_dom_data(
        title=title,
        time_info=time_info,
        event_date=event_date,
    )


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
            timed_event_pairs: list[tuple[Event, object]] = []
            last_data_eventid_count = 0

            # Google Calendar は描画が遅れることがあるため、0件時は再試行する
            for attempt in range(1, 4):
                # 週の日付を取得
                week_dates = await _extract_week_dates(page)
                events = []

                # 終日イベントの取得
                try:
                    all_day_events = await _extract_all_day_events(page, week_dates)
                    events.extend(all_day_events)
                except Exception as e:
                    logger.warning(f"終日イベント取得失敗: {e}")

                # 時間指定イベントの取得
                try:
                    timed_event_pairs = await _extract_timed_events(page, week_dates)
                    timed_events = [event for event, _ in timed_event_pairs]
                    events.extend(timed_events)
                except Exception as e:
                    logger.warning(f"時間指定イベント取得失敗: {e}")
                    timed_events = []
                    timed_event_pairs = []

                last_data_eventid_count = await page.locator('[data-eventid]').count()
                logger.info(
                    "時間指定イベント解析: %d 件 (data-eventid=%d, attempt=%d)",
                    len(timed_events),
                    last_data_eventid_count,
                    attempt,
                )

                if events:
                    break

                if attempt < 3:
                    logger.warning(
                        "予定を0件検出。週ビューを再読み込みして再試行します (attempt=%d)",
                        attempt,
                    )
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

            if not events:
                logger.warning(
                    "再試行後も0件でした (data-eventid=%d)。",
                    last_data_eventid_count,
                )

            # 各イベントの詳細を取得（会議URL等）
            # 抽出時と同じ要素に対して処理しないと URL が別イベントにずれるため、
            # _extract_timed_events で保持した対応ペアを使う。
            all_day_count = len([e for e in events if e.is_all_day])
            detail_limit = min(len(timed_event_pairs), 5)
            if detail_limit < len(timed_event_pairs):
                logger.info(
                    "イベント詳細取得を制限: %d/%d 件",
                    detail_limit,
                    len(timed_event_pairs),
                )

            for i in range(detail_limit):
                event_index = all_day_count + i
                _, element = timed_event_pairs[i]
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
