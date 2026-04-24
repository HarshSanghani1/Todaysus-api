"""
Web searcher - finds fresh trending news topics via Google News first,
then DuckDuckGo HTML search as a fallback.
"""
import datetime
import email.utils
import html
import logging
import random
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

from autoposting_agent.config import HOURLY_FOCUSED_KEYWORDS, SEARCH_TOPICS

logger = logging.getLogger("autoposting_agent.searcher")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

FRESHNESS_WINDOW_HOURS = 24
DDG_DATE_FILTER = "d"
FRESH_QUERY_TERMS = tuple(HOURLY_FOCUSED_KEYWORDS)

STALE_YEAR_RE = re.compile(r"\b(?:2021|2022|2023)\b")
STALE_TEXT_RE = re.compile(
    r"\b(?:archived?|cached|months?\s+ago|years?\s+ago|last\s+month|last\s+year)\b",
    re.IGNORECASE,
)
RELATIVE_TIME_RE = re.compile(
    r"\b(?:(just\s+now|right\s+now|now|today|live)|"
    r"(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\s+ago)\b",
    re.IGNORECASE,
)


def search_trending_topic() -> dict:
    """
    Pick a random search topic, search fresh news sources, and return a dict
    with the best headline + snippet for article generation.
    """
    topic = random.choice(SEARCH_TOPICS)
    fresh_query = _build_fresh_query(topic)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    utc_now_iso = utc_now.isoformat()

    logger.info("Searching for fresh topic: %s (UTC: %s)", fresh_query, utc_now_iso)

    google_result = search_google_news(topic, utc_now_iso, utc_now, fresh_query)
    if google_result:
        return google_result

    ddg_result = search_duckduckgo(topic, utc_now_iso, utc_now, fresh_query)
    if ddg_result:
        return ddg_result

    logger.warning("No fresh search results passed filtering. Falling back to base topic.")
    return {
        "title": topic,
        "snippet": f"Latest developments in {topic}",
        "search_topic": topic,
        "timestamp_utc": utc_now_iso,
        "source": "fallback",
        "freshness": "unverified",
    }


def search_google_news(
    topic: str,
    utc_now: str | None = None,
    now: datetime.datetime | None = None,
    fresh_query: str | None = None,
) -> dict | None:
    """
    Search Google News RSS first. Google News RSS includes publish timestamps,
    which lets us enforce a real 24-hour freshness window.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    utc_now = utc_now or now.isoformat()
    fresh_query = fresh_query or _build_fresh_query(topic)
    google_query = f"{fresh_query} when:1d"

    try:
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(google_query)}&hl=en-US&gl=US&ceid=US:en"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        fresh_results = []

        for item in items[:15]:
            raw_title = item.findtext("title") or ""
            title = html.unescape(raw_title).strip()
            clean_title = title.split(" - ")[0].strip()
            snippet = _strip_html(item.findtext("description") or "")
            published_at = _parse_rss_datetime(item.findtext("pubDate"))

            if not clean_title or len(clean_title) <= 15:
                continue

            if not _passes_freshness_filter(
                clean_title,
                snippet,
                now=now,
                published_at=published_at,
                require_date=True,
            ):
                logger.info("Discarded stale Google News result: %s", clean_title)
                continue

            fresh_results.append({
                "title": clean_title,
                "snippet": snippet or f"Latest updates on {topic}",
                "search_topic": topic,
                "timestamp_utc": utc_now,
                "source": "google_news",
                "published_at": published_at.isoformat() if published_at else None,
                "freshness": "past_24h",
            })

        if fresh_results:
            chosen = random.choice(fresh_results[:5])
            logger.info("Picked topic from Google News: %s", chosen["title"])
            return chosen

        logger.warning("No Google News RSS results passed the freshness filter.")

    except Exception as e:
        logger.error("Google News search error: %s", e)

    return None


def search_duckduckgo(
    topic: str,
    utc_now: str | None = None,
    now: datetime.datetime | None = None,
    fresh_query: str | None = None,
) -> dict | None:
    """
    Fallback search using DuckDuckGo HTML with df=d and an extra stale-date
    snippet filter. Results without a visible date are allowed only after the
    DuckDuckGo day filter has already narrowed the page.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    utc_now = utc_now or now.isoformat()
    fresh_query = fresh_query or _build_fresh_query(topic)

    try:
        url = (
            "https://html.duckduckgo.com/html/?"
            f"q={quote_plus(fresh_query)}&df={DDG_DATE_FILTER}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        page_html = resp.text

        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', page_html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</td>', page_html, re.DOTALL)

        results = []
        for i, title in enumerate(titles[:15]):
            clean_title = _strip_html(title)
            clean_snippet = _strip_html(snippets[i]) if i < len(snippets) else ""

            if not clean_title or len(clean_title) <= 15:
                continue

            if not _passes_freshness_filter(
                clean_title,
                clean_snippet,
                now=now,
                published_at=None,
                require_date=False,
            ):
                logger.info("Discarded stale DuckDuckGo result: %s", clean_title)
                continue

            results.append({
                "title": clean_title,
                "snippet": clean_snippet,
                "search_topic": topic,
                "timestamp_utc": utc_now,
                "source": "duckduckgo",
                "freshness": "past_24h_or_no_stale_signal",
            })

        if results:
            chosen = random.choice(results[:5])
            logger.info("Picked topic from DuckDuckGo: %s", chosen["title"])
            return chosen

        logger.warning("No DuckDuckGo results passed the freshness filter.")

    except Exception as e:
        logger.error("DuckDuckGo search error: %s", e)

    return None


def _build_fresh_query(topic: str) -> str:
    """Append freshness terms while keeping the topic readable."""
    words = topic.split()
    existing = topic.lower()
    additions = [term for term in FRESH_QUERY_TERMS if term not in existing]
    return " ".join(words + additions)


def _strip_html(value: str) -> str:
    """Remove tags/entities and normalize whitespace from scraped text."""
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    decoded = html.unescape(without_tags)
    return re.sub(r"\s+", " ", decoded).strip()


def _parse_rss_datetime(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _passes_freshness_filter(
    title: str,
    snippet: str,
    *,
    now: datetime.datetime,
    published_at: datetime.datetime | None,
    require_date: bool,
) -> bool:
    combined = f"{title} {snippet}".lower()

    if STALE_YEAR_RE.search(combined) or STALE_TEXT_RE.search(combined):
        return False

    if published_at is not None:
        age_hours = (now - published_at).total_seconds() / 3600
        if not 0 <= age_hours <= FRESHNESS_WINDOW_HOURS:
            return False

        relative_age = _extract_relative_age_hours(combined)
        return relative_age is None or relative_age <= FRESHNESS_WINDOW_HOURS

    relative_age = _extract_relative_age_hours(combined)
    if relative_age is not None:
        return relative_age <= FRESHNESS_WINDOW_HOURS

    return not require_date


def _extract_relative_age_hours(text: str) -> float | None:
    """
    Extract the freshest visible relative timestamp from a snippet.
    Returns None if no relative timestamp is present.
    """
    ages = []
    for match in RELATIVE_TIME_RE.finditer(text):
        immediate_marker, number, unit = match.groups()
        if immediate_marker:
            ages.append(0.0)
            continue

        quantity = int(number)
        unit = unit.lower()
        if unit.startswith(("minute", "min")):
            ages.append(quantity / 60)
        elif unit.startswith(("hour", "hr")):
            ages.append(float(quantity))
        elif unit.startswith("day"):
            ages.append(quantity * 24.0)
        elif unit.startswith("week"):
            ages.append(quantity * 24.0 * 7)
        elif unit.startswith("month"):
            ages.append(quantity * 24.0 * 30)
        elif unit.startswith("year"):
            ages.append(quantity * 24.0 * 365)

    return min(ages) if ages else None
