"""
Single-cycle runner for GitHub Actions / Render Cron Jobs.

Local test commands:
  python -m autoposting_agent.run_once --scrape-only
  python -m autoposting_agent.run_once --scrape-only --url "https://example.com/article"
  python -m autoposting_agent.run_once --dry-run

Cron command:
  python -m autoposting_agent.run_once
"""
import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

_agent_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_agent_dir, ".env"))
load_dotenv()

from autoposting_agent.article_generator import generate_article
from autoposting_agent.config import NVIDIA_API_KEY
from autoposting_agent.publisher import ensure_topics_exist, get_internal_links, is_duplicate, publish_article
from autoposting_agent.web_searcher import MIN_SOURCE_WORDS, scrape_source_url, search_trending_topic

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-35s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("autoposting_agent")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one autoposting cycle.")
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only search and scrape source text. No model call, DB check, or publish.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search, scrape, and generate, but do not publish to MongoDB.",
    )
    parser.add_argument(
        "--url",
        help="Scrape this exact source URL instead of searching for a random trending topic.",
    )
    parser.add_argument(
        "--title",
        help="Optional title to use with --url.",
    )
    return parser.parse_args()


def _log_scrape_result(search_result: dict) -> None:
    source_text = search_result.get("source_text", "")
    preview = source_text[:500].replace("\n", " ")
    logger.info("Scraped title: %s", search_result.get("title", ""))
    logger.info("Source URL: %s", search_result.get("source_url", ""))
    logger.info("Source words: %s", search_result.get("source_word_count", 0))
    logger.info("Snippet: %s", search_result.get("snippet", "")[:300])
    logger.info("Source preview: %s%s", preview, "..." if len(source_text) > 500 else "")


_STOP_WORDS = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this",
    "from", "have", "has", "had", "not", "but", "its", "news", "today",
    "live", "latest", "updates", "breaking", "what", "how", "why",
    "after", "amid", "over", "into", "will", "amid", "amid", "amid",
}

def _seed_topics(search_result: dict) -> list[dict]:
    """Extract meaningful entity-level keywords from the article title for DB link seeding.
    Using the title (not the raw search_topic string) avoids fetching unrelated internal links.
    """
    title = search_result.get("title", "") or search_result.get("search_topic", "")
    words = re.findall(r"[A-Za-z][a-z]{2,}", title)
    seeds = [
        w for w in words
        if len(w) > 3 and w.lower() not in _STOP_WORDS
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[dict] = []
    for w in seeds:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            unique.append({"name": w, "slug": lw})
    return unique[:6]


def run_once() -> None:
    args = _parse_args()

    logger.info("=" * 60)
    logger.info("TodaysUS AutoPosting Agent - Single Run")
    logger.info("%s", datetime.now(timezone.utc).isoformat())
    logger.info("=" * 60)

    logger.info("Step 1/4: Searching and scraping source text...")
    if args.url:
        search_result = scrape_source_url(args.url, title=args.title)
    else:
        search_result = search_trending_topic()
    if not search_result or not search_result.get("title"):
        logger.error("No search results. Exiting.")
        sys.exit(1)

    _log_scrape_result(search_result)

    source_words = int(search_result.get("source_word_count") or 0)
    if args.scrape_only:
        if source_words >= MIN_SOURCE_WORDS:
            logger.info("Scrape-only check passed. Source is ready for grounded generation.")
            sys.exit(0)
        logger.error(
            "Scrape-only check failed. Need at least %s source words, got %s.",
            MIN_SOURCE_WORDS,
            source_words,
        )
        sys.exit(2)

    if not NVIDIA_API_KEY:
        logger.error("NVIDIA_API_KEY not set. Add it to local .env, GitHub, or Render env vars.")
        sys.exit(1)

    logger.info("Step 2/4: Fetching internal link candidates from DB...")
    seed_topics = _seed_topics(search_result)
    ensure_topics_exist(seed_topics)
    internal_links = get_internal_links(seed_topics, limit=8)
    logger.info("%s internal link(s) found.", len(internal_links))

    logger.info("Step 3/4: Generating grounded article via NVIDIA API...")
    article_data = generate_article(search_result, internal_links=internal_links)
    if not article_data:
        logger.error("Generation failed. Exiting.")
        sys.exit(1)

    word_count = len(article_data.get("content_html", "").split())
    title = article_data["title"]
    quality = article_data.get("quality_score", 0)
    featured = article_data.get("is_featured", False)
    structure = article_data.get("article_structure", "unknown")

    logger.info("Generated title (%s chars): %s", len(title), title)
    logger.info("Structure: %s | Quality: %s/10 | Featured: %s", structure, quality, featured)
    logger.info("Generated article length: ~%s words", word_count)
    logger.info("Grounded on: %s (%s source words)", article_data.get("source_url", ""), source_words)

    if args.dry_run:
        logger.info("Dry run complete. Article was generated but not published.")
        sys.exit(0)

    if is_duplicate(article_data["title"]):
        logger.warning("Duplicate: %s. Skipping.", article_data["title"])
        sys.exit(0)

    logger.info("Step 4/4: Publishing to MongoDB...")
    result = publish_article(article_data)
    if result:
        tag = "FEATURED " if featured else ""
        logger.info("SUCCESS! %sPublished: %s", tag, result["slug"])
        sys.exit(0)

    logger.error("Publish failed.")
    sys.exit(1)


if __name__ == "__main__":
    run_once()
