"""
Web searcher — finds trending news topics via DuckDuckGo HTML search and Google News.
No API key required.
"""
import re
import random
import logging
import requests
import datetime
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from autoposting_agent.config import SEARCH_TOPICS

logger = logging.getLogger("autoposting_agent.searcher")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def search_trending_topic() -> dict:
    """
    Pick a random search topic, scrape DuckDuckGo HTML results with date filters,
    and return a dict with the best headline + snippet for article generation.
    """
    topic = random.choice(SEARCH_TOPICS)
    utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logger.info(f"🔍 Searching for: {topic} (UTC: {utc_now})")

    try:
        # df=d means "past day" (24h). df=w means "past week". 
        # Using df=d for maximum freshness as requested.
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(topic)}&df=d"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Extract result titles and snippets
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</td>', html, re.DOTALL)

        results = []
        for i, title in enumerate(titles[:10]):
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            if clean_title and len(clean_title) > 15:
                results.append({
                    "title": clean_title,
                    "snippet": clean_snippet,
                    "search_topic": topic,
                    "timestamp_utc": utc_now
                })

        if not results:
            logger.warning("No DuckDuckGo results found, trying Google News RSS...")
            return search_google_news(topic, utc_now)

        # Pick a random result from top 5 for variety
        chosen = random.choice(results[:5])
        logger.info(f"📰 Picked topic from DDG: {chosen['title']}")
        return chosen

    except Exception as e:
        logger.error(f"Search error: {e}")
        return search_google_news(topic, utc_now)


def search_google_news(topic: str, utc_now: str) -> dict:
    """
    Fallback search using Google News RSS (v. fresh).
    """
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(topic)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        
        root = ET.fromstring(resp.text)
        items = root.findall('.//item')
        
        if items:
            # Pick one of the first 3 items
            item = random.choice(items[:3])
            title = item.find('title').text
            # Title usually contains " - Source", let's clean it
            clean_title = title.split(' - ')[0]
            snippet = item.find('description').text
            # Description is often HTML or empty, but title is usually good enough
            clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            
            logger.info(f"📰 Picked topic from Google News: {clean_title}")
            return {
                "title": clean_title,
                "snippet": clean_snippet or f"Latest updates on {topic}",
                "search_topic": topic,
                "timestamp_utc": utc_now
            }
    except Exception as e:
        logger.error(f"Google News fallback error: {e}")

    return {
        "title": topic,
        "snippet": f"Latest developments in {topic}",
        "search_topic": topic,
        "timestamp_utc": utc_now
    }
