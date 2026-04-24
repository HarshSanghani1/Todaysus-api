"""
Single-cycle runner for GitHub Actions / Render Cron Jobs.

GitHub Actions / Render calls this script on schedule → runs ONE cycle → exits.
No APScheduler needed — the scheduler IS the external cron.

Usage (local test):
  python -m autoposting_agent.run_once

GitHub Actions / Render Cron Command:
  python -m autoposting_agent.run_once
"""
import sys
import os
import logging
from datetime import datetime

from dotenv import load_dotenv

# Load .env from autoposting_agent dir first, then root
_agent_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_agent_dir, ".env"))
load_dotenv()  # also try root .env as fallback

from autoposting_agent.config import NVIDIA_API_KEY
from autoposting_agent.web_searcher import search_trending_topic
from autoposting_agent.article_generator import MIN_PUBLISH_WORDS, generate_article
from autoposting_agent.publisher import publish_article, is_duplicate, get_internal_links

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-35s │ %(levelname)-5s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("autoposting_agent")


def run_once():
    """Execute a single search → generate → publish cycle, then exit."""
    logger.info("=" * 60)
    logger.info("🤖 TodaysUS AutoPosting Agent — Single Run")
    logger.info(f"🕐 {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 60)

    # Verify API key
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY not set! Add it to GitHub / Render env vars.")
        sys.exit(1)

    # ── Step 1: Search ───────────────────────────────────────────────────────
    logger.info("📡 Step 1/4: Searching for trending topics...")
    search_result = search_trending_topic()

    if not search_result or not search_result.get("title"):
        logger.error("❌ No search results. Exiting.")
        sys.exit(1)

    logger.info(f"   → {search_result['title']}")

    # ── Step 2: Fetch internal link candidates from DB ───────────────────────
    logger.info("🔗 Step 2/4: Fetching internal link candidates from DB...")
    seed_topics = [
        {"name": w, "slug": w.lower().replace(" ", "-")}
        for w in search_result.get("search_topic", "").split()
        if len(w) > 3
    ][:5]
    internal_links = get_internal_links(seed_topics, limit=8)
    logger.info(f"   → {len(internal_links)} internal link(s) found")

    # ── Step 3: Generate ─────────────────────────────────────────────────────
    logger.info("🤖 Step 3/4: Generating article via NVIDIA API...")
    article_data = generate_article(search_result, internal_links=internal_links)

    if not article_data:
        logger.error("❌ Generation failed. Exiting.")
        sys.exit(1)

    word_count = int(
        article_data.get("word_count")
        or len(article_data.get("content_html", "").split())
    )
    if word_count < MIN_PUBLISH_WORDS:
        logger.error(
            "❌ Article below publishable length (%s words; minimum %s). Exiting.",
            word_count,
            MIN_PUBLISH_WORDS,
        )
        sys.exit(1)

    # Duplicate check
    if is_duplicate(article_data["title"]):
        logger.warning(f"⚠️  Duplicate: {article_data['title']}. Skipping.")
        sys.exit(0)

    title = article_data["title"]
    quality = article_data.get("quality_score", 0)
    featured = article_data.get("is_featured", False)
    structure = article_data.get("article_structure", "unknown")

    logger.info(f"   → Title ({len(title)} chars): {title}")
    logger.info(f"   → Structure: {structure} | Quality: {quality}/10 | Featured: {featured}")
    logger.info(f"   → ~{word_count} words")

    # ── Step 4: Publish ──────────────────────────────────────────────────────
    logger.info("📤 Step 4/4: Publishing to MongoDB...")
    result = publish_article(article_data)

    if result:
        tag = "⭐ FEATURED " if featured else ""
        logger.info(f"🎉 SUCCESS! {tag}Published: {result['slug']}")
        sys.exit(0)
    else:
        logger.error("❌ Publish failed.")
        sys.exit(1)


if __name__ == "__main__":
    run_once()
