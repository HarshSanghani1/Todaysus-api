"""
Web searcher — finds trending news topics via DuckDuckGo HTML search.
No API key required.
"""
import re
import random
import logging
import requests
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
    Pick a random search topic, scrape DuckDuckGo HTML results,
    and return a dict with the best headline + snippet for article generation.
    """
    topic = random.choice(SEARCH_TOPICS)
    logger.info(f"🔍 Searching for: {topic}")

    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(topic)}"
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
                    "search_topic": topic
                })

        if not results:
            logger.warning("No results found, using fallback topic")
            return {
                "title": topic,
                "snippet": f"Latest developments in {topic}",
                "search_topic": topic
            }

        # Pick a random result from top 5 for variety
        chosen = random.choice(results[:5])
        logger.info(f"📰 Picked topic: {chosen['title']}")
        return chosen

    except Exception as e:
        logger.error(f"Search error: {e}")
        return {
            "title": topic,
            "snippet": f"Latest developments in {topic}",
            "search_topic": topic
        }
