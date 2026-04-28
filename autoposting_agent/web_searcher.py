"""
Web searcher - finds trending news topics and fetches source text for grounding.
No API key required.
"""
import datetime
import html
import json
import logging
import random
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, quote_plus, unquote, urljoin, urlparse

import requests

from autoposting_agent.config import SEARCH_TOPICS

logger = logging.getLogger("autoposting_agent.searcher")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

MIN_SOURCE_WORDS = 180
MAX_SOURCE_CHARS = 14000

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

MIN_SOURCE_WORDS = 180
MAX_SOURCE_CHARS = 14000


class ReadableTextParser(HTMLParser):
    """Extract readable article-like text without adding third-party dependencies."""

    CAPTURE_TAGS = {"h1", "h2", "h3", "p", "li", "blockquote", "td", "th"}
    SKIP_TAGS = {"script", "style", "noscript", "svg", "form", "nav", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._capture_depth = 0
        self._current = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if self._skip_depth == 0 and tag in self.CAPTURE_TAGS:
            self._flush()
            self._capture_depth += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._skip_depth == 0 and tag in self.CAPTURE_TAGS:
            self._flush()
            self._capture_depth = max(0, self._capture_depth - 1)
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and self._capture_depth > 0:
            cleaned = _clean_text(data)
            if cleaned:
                self._current.append(cleaned)

    def close(self):
        self._flush()
        super().close()

    def _flush(self):
        if not self._current:
            return
        text = _clean_text(" ".join(self._current))
        self._current = []
        if _is_useful_block(text):
            self.blocks.append(text)


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_useful_block(text: str) -> bool:
    if len(text) < 35:
        return False
    lowered = text.lower()
    boilerplate_markers = [
        "accept cookies",
        "all rights reserved",
        "subscribe",
        "sign up for",
        "privacy policy",
        "terms of service",
        "advertisement",
        "enable javascript",
    ]
    return not any(marker in lowered for marker in boilerplate_markers)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _resolve_duckduckgo_url(raw_url: str) -> str:
    raw_url = html.unescape(raw_url or "").strip()
    if not raw_url:
        return ""

    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    elif raw_url.startswith("/"):
        raw_url = urljoin("https://duckduckgo.com", raw_url)

    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        if query.get("uddg"):
            return unquote(query["uddg"][0])

    return raw_url


def _resolve_bing_news_url(raw_url: str) -> str:
    raw_url = html.unescape(raw_url or "").strip()
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    if "bing.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        if query.get("url"):
            return unquote(query["url"][0])

    return raw_url


def fetch_article_text(source_url: str) -> str:
    """Fetch a result URL and return cleaned article-like text."""
    if not source_url:
        return ""

    try:
        resp = requests.get(source_url, headers=HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" not in content_type and "text" not in content_type:
            logger.info("Skipping non-HTML source: %s", source_url)
            return ""

        page_html = resp.text[:1_500_000]
        page_html = re.sub(r"(?is)<(script|style|noscript|svg|form).*?</\1>", " ", page_html)

        parser = ReadableTextParser()
        parser.feed(page_html)
        parser.close()

        source_text = "\n\n".join(parser.blocks)
        if _word_count(source_text) < MIN_SOURCE_WORDS:
            api_text = fetch_wordpress_api_text(source_url)
            if _word_count(api_text) > _word_count(source_text):
                source_text = api_text

        if len(source_text) > MAX_SOURCE_CHARS:
            source_text = source_text[:MAX_SOURCE_CHARS].rsplit(" ", 1)[0]
        return source_text.strip()

    except (requests.exceptions.Timeout, TimeoutError) as exc:
        logger.debug("Timeout fetching %s: %s", source_url, exc)
        return ""
    except requests.exceptions.RequestException as exc:
        logger.debug("Request error fetching %s: %s", source_url, exc)
        return ""
    except Exception as exc:
        logger.warning("Could not fetch source text from %s: %s", source_url, exc)
        return ""


def fetch_wordpress_api_text(source_url: str) -> str:
    """Fetch content from WordPress JSON routes used by some static/SPAs."""
    parsed = urlparse(source_url)
    slug = parsed.path.strip("/").split("/")[-1]
    if not parsed.scheme or not parsed.netloc or not slug:
        return ""

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    wp_path = f"/wp-json/wp/v2/posts?slug={quote(slug)}&per_page=1"
    candidate_urls = [
        f"{base_url}/api/fetch?path={quote(wp_path, safe='')}",
        f"{base_url}{wp_path}",
    ]

    for api_url in candidate_urls:
        try:
            resp = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
            resp.raise_for_status()

            try:
                payload = resp.json()
            except json.JSONDecodeError:
                continue

            post = payload[0] if isinstance(payload, list) and payload else None
            if not isinstance(post, dict):
                continue

            title = _clean_text(post.get("title", {}).get("rendered", ""))
            excerpt = _clean_text(post.get("excerpt", {}).get("rendered", ""))
            content = _clean_text(post.get("content", {}).get("rendered", ""))
            acf = post.get("acf", {}) if isinstance(post.get("acf"), dict) else {}
            acf_content = _clean_text(acf.get("english_content", ""))

            parts = [part for part in [title, excerpt, content, acf_content] if part]
            source_text = "\n\n".join(dict.fromkeys(parts))
            if source_text:
                logger.info("Fetched WordPress API source with %s words: %s", _word_count(source_text), api_url)
                return source_text

        except Exception as exc:
            logger.info("WordPress API fallback failed for %s: %s", api_url, exc)

    return ""


def _extract_duckduckgo_results(page_html: str, topic: str, utc_now: str) -> list[dict]:
    anchors = re.findall(r'(<a[^>]+class="result__a"[^>]*>)(.*?)</a>', page_html, re.DOTALL)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</td>', page_html, re.DOTALL)

    results = []
    for i, (start_tag, anchor_html) in enumerate(anchors[:10]):
        href_match = re.search(r'href="([^"]+)"', start_tag)
        clean_title = _clean_text(anchor_html)
        clean_snippet = _clean_text(snippets[i]) if i < len(snippets) else ""
        source_url = _resolve_duckduckgo_url(href_match.group(1) if href_match else "")

        if clean_title and len(clean_title) > 15:
            results.append(
                {
                    "title": clean_title,
                    "snippet": clean_snippet,
                    "source_url": source_url,
                    "search_topic": topic,
                    "timestamp_utc": utc_now,
                }
            )
    return results


def _attach_source_text(results: list[dict]) -> dict | None:
    if not results:
        return None

    fallback = None
    for result in results[:6]:
        source_text = fetch_article_text(result.get("source_url", ""))
        word_count = _word_count(source_text)
        result["source_text"] = source_text
        result["source_word_count"] = word_count

        if fallback is None or word_count > fallback.get("source_word_count", 0):
            fallback = result

        if word_count >= MIN_SOURCE_WORDS:
            logger.info(
                "Picked source with %s words: %s",
                word_count,
                result.get("title", ""),
            )
            return result

    if fallback:
        logger.warning(
            "No source reached %s words; best had %s words: %s",
            MIN_SOURCE_WORDS,
            fallback.get("source_word_count", 0),
            fallback.get("title", ""),
        )
    return fallback


def _search_one_topic(topic: str, utc_now: str) -> dict:
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(topic)}&df=d"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        results = _extract_duckduckgo_results(resp.text, topic, utc_now)
        chosen = _attach_source_text(results)
        if chosen:
            logger.info("Picked topic from DDG: %s", chosen["title"])
            return chosen

        logger.warning("No DuckDuckGo results found, trying Bing News RSS...")
        return search_bing_news(topic, utc_now)

    except Exception as exc:
        logger.error("Search error: %s", exc)
        return search_bing_news(topic, utc_now)


def search_trending_topic(max_topic_attempts: int = 6) -> dict:
    """
    Try several random search topics, fetch source text, and return the first
    result with enough grounding material.
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    topics = random.sample(SEARCH_TOPICS, k=min(max_topic_attempts, len(SEARCH_TOPICS)))
    best_result = None

    for idx, topic in enumerate(topics, start=1):
        logger.info("Searching for: %s (attempt %s/%s, UTC: %s)", topic, idx, len(topics), utc_now)
        result = _search_one_topic(topic, utc_now)
        source_words = int(result.get("source_word_count") or 0) if result else 0

        if result and (best_result is None or source_words > best_result.get("source_word_count", 0)):
            best_result = result

        if source_words >= MIN_SOURCE_WORDS:
            return result

        logger.warning("Attempt %s had only %s source words; trying another topic.", idx, source_words)

    if best_result:
        logger.warning(
            "No attempted topic reached %s source words; returning best result with %s words.",
            MIN_SOURCE_WORDS,
            best_result.get("source_word_count", 0),
        )
        return best_result

    topic = topics[0] if topics else "breaking news US today"
    return {
        "title": topic,
        "snippet": f"Latest developments in {topic}",
        "source_url": "",
        "source_text": "",
        "source_word_count": 0,
        "search_topic": topic,
        "timestamp_utc": utc_now,
    }


def scrape_source_url(source_url: str, title: str | None = None, search_topic: str = "manual source URL") -> dict:
    """Build a search_result-like object from a specific URL for local testing."""
    utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    source_text = fetch_article_text(source_url)
    source_word_count = _word_count(source_text)
    clean_title = title or ""

    if not clean_title and source_text:
        clean_title = source_text.splitlines()[0].strip()

    if not clean_title:
        parsed = urlparse(source_url)
        clean_title = parsed.path.strip("/").split("/")[-1].replace("-", " ").title()

    snippet = source_text[:280].replace("\n", " ").strip() if source_text else ""
    return {
        "title": clean_title,
        "snippet": snippet,
        "source_url": source_url,
        "source_text": source_text,
        "source_word_count": source_word_count,
        "search_topic": search_topic,
        "timestamp_utc": utc_now,
    }


def search_bing_news(topic: str, utc_now: str) -> dict:
    """Fallback search using Bing News RSS, which usually includes publisher URLs."""
    try:
        url = f"https://www.bing.com/news/search?q={quote_plus(topic)}&format=rss&cc=US&setlang=en-US"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = root.findall(".//item")

        results = []
        for item in items[:8]:
            clean_title = _clean_text(item.findtext("title", ""))
            snippet = _clean_text(item.findtext("description", ""))
            source_url = _resolve_bing_news_url(item.findtext("link", "") or "")

            if clean_title:
                results.append(
                    {
                        "title": clean_title,
                        "snippet": snippet or f"Latest updates on {topic}",
                        "source_url": source_url,
                        "search_topic": topic,
                        "timestamp_utc": utc_now,
                    }
                )

        chosen = _attach_source_text(results)
        if chosen and chosen.get("source_word_count", 0) >= MIN_SOURCE_WORDS:
            logger.info("Picked topic from Bing News: %s", chosen["title"])
            return chosen

        logger.warning("Bing News did not provide enough source text, trying Google News RSS...")
        return search_google_news(topic, utc_now)

    except Exception as exc:
        logger.error("Bing News fallback error: %s", exc)
        return search_google_news(topic, utc_now)


def search_google_news(topic: str, utc_now: str) -> dict:
    """Fallback search using Google News RSS."""
    try:
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(topic)}&hl=en-US&gl=US&ceid=US:en"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = root.findall(".//item")

        results = []
        for item in items[:8]:
            raw_title = item.findtext("title", "")
            clean_title = raw_title.split(" - ")[0].strip() if raw_title else ""
            snippet = _clean_text(item.findtext("description", ""))
            source_link = item.findtext("link", "") or ""
            
            if clean_title and len(clean_title) > 15:
                results.append(
                    {
                        "title": clean_title,
                        "snippet": snippet or f"Latest updates on {topic}",
                        "source_url": source_link,
                        "search_topic": topic,
                        "timestamp_utc": utc_now,
                    }
                )

        chosen = _attach_source_text(results)
        if chosen:
            logger.info("Picked topic from Google News: %s", chosen["title"])
            return chosen

    except Exception as exc:
        logger.error("Google News fallback error: %s", exc)

    return {
        "title": topic,
        "snippet": f"Latest developments in {topic}",
        "source_url": "",
        "source_text": "",
        "source_word_count": 0,
        "search_topic": topic,
        "timestamp_utc": utc_now,
    }
