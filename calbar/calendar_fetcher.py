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
WEEK_VIEW_URL = "https://calendar.google.com/calendar/r/week"
# Google Calendar へのアクセスを前提とした認証 URL
# 未認証時に calendar.google.com を開くと商品紹介ページにリダイレクトされるため、
# accounts.google.com 経由で認証後に Calendar へ遷移させる
AUTH_URL = (
    "https://accounts.google.com/ServiceLogin"
    "?continue=https://calendar.google.com/calendar/r/week"
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


async def _extract_timed_events(page: Page, week_dates: list[date]) -> list[Event]:
    """時間指定イベントを抽出"""
    events = []

    # イベントチップを取得 - aria-label と role 属性を使用
    event_elements = await page.query_selector_all(
        '[data-eventid]:not([data-allday="true"]), '
        '[role="button"][data-eventchip]'
    )

    processed_labels = set()

    for element in event_elements:
        aria_label = await element.get_attribute('aria-label') or ''
        if not aria_label:
            aria_label = await element.text_content() or ''

        aria_label = aria_label.strip()
        if not aria_label or aria_label in processed_labels:
            continue
        processed_labels.add(aria_label)

        # aria-label パターン: "イベントタイトル, 2月14日 金曜日, 9:00～10:00"
        # または: "9:00 - 10:00, イベントタイトル"
        event_data = _parse_aria_label(aria_label, week_dates)
        if event_data:
            events.append(event_data)

    return events


def _parse_aria_label(label: str, week_dates: list[date]) -> Optional[Event]:
    """aria-label テキストからイベント情報をパース"""
    # 時刻パターン
    time_range_pattern = re.compile(
        r'(\d{1,2}:\d{2})\s*[–—-～〜]\s*(\d{1,2}:\d{2})'
    )
    time_match = time_range_pattern.search(label)

    if not time_match:
        return None

    time_info = f"{time_match.group(1)} - {time_match.group(2)}"

    # タイトル抽出: 時刻部分を除いた残りからタイトルを取得
    title = label
    # 時刻部分を除去
    title = time_range_pattern.sub('', title)
    # 日付部分を除去（例: "2月14日 金曜日"）
    date_pattern = re.compile(r'\d{1,2}月\d{1,2}日\s*[月火水木金土日]曜日?')
    title = date_pattern.sub('', title)
    # カンマや余分な空白を除去
    title = re.sub(r'[,、]\s*', ' ', title).strip()
    title = re.sub(r'\s+', ' ', title).strip()

    if not title:
        title = "（タイトルなし）"

    # 日付を推定
    event_date = _extract_date_from_label(label, week_dates)

    return parse_event_from_dom_data(
        title=title,
        time_info=time_info,
        event_date=event_date,
    )


def _extract_date_from_label(label: str, week_dates: list[date]) -> date:
    """aria-label から日付を抽出"""
    # "2月14日" パターン
    date_match = re.search(r'(\d{1,2})月(\d{1,2})日', label)
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
    try:
        await element.click()
        await page.wait_for_timeout(500)

        # 詳細ポップアップからテキストを取得
        detail_panel = await page.query_selector(
            '[role="dialog"], [data-eventdetails], .ecHOqf'
        )
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

        # ポップアップを閉じる
        close_btn = await page.query_selector(
            '[aria-label="閉じる"], [aria-label="Close"], button[aria-label*="close"]'
        )
        if close_btn:
            await close_btn.click()
        else:
            await page.keyboard.press('Escape')
        await page.wait_for_timeout(300)

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
            await page.goto(WEEK_VIEW_URL, wait_until="networkidle")

            if not await is_authenticated(page):
                await browser.close()
                logger.info("認証が必要です。ブラウザを起動します...")
                await authenticate(config)
                # 認証後にリトライ
                return await fetch_events(config)

            # ページの読み込みを待つ
            await page.wait_for_timeout(2000)

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
                timed_events = await _extract_timed_events(page, week_dates)
                events.extend(timed_events)
            except Exception as e:
                logger.warning(f"時間指定イベント取得失敗: {e}")

            # 各イベントの詳細を取得（会議URL等）
            # 再度イベント要素を取得して詳細を開く
            event_elements = await page.query_selector_all(
                '[data-eventid], [role="button"][data-eventchip]'
            )
            for i, element in enumerate(event_elements):
                if i < len(events):
                    events[i] = await _get_event_detail(page, element, events[i])

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
