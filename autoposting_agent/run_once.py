"""
Single-cycle runner for Render Cron Jobs.

Render calls this script on schedule → it runs ONE cycle → exits.
No APScheduler needed — Render IS the scheduler.

Usage (local test):
  python -m autoposting_agent.run_once

Render Cron Command:
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
from autoposting_agent.article_generator import generate_article
from autoposting_agent.publisher import publish_article, is_duplicate

# ── Logging ─────────────────────────────────────────────────────────────────
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
    logger.info(f"🤖 TodaysUS AutoPosting Agent — Single Run")
    logger.info(f"🕐 {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 60)

    # Verify API key
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY not set! Add it to Render env vars.")
        sys.exit(1)

    # Step 1: Search
    logger.info("📡 Step 1/3: Searching for trending topics...")
    search_result = search_trending_topic()

    if not search_result or not search_result.get("title"):
        logger.error("❌ No search results. Exiting.")
        sys.exit(1)

    logger.info(f"   → {search_result['title']}")

    # Step 2: Generate
    logger.info("🤖 Step 2/3: Generating article via NVIDIA API...")
    article_data = generate_article(search_result)

    if not article_data:
        logger.error("❌ Generation failed. Exiting.")
        sys.exit(1)

    # Duplicate check
    if is_duplicate(article_data["title"]):
        logger.warning(f"⚠️  Duplicate: {article_data['title']}. Skipping.")
        sys.exit(0)

    word_count = len(article_data.get("content_html", "").split())
    logger.info(f"   → {article_data['title']} (~{word_count} words)")

    # Step 3: Publish
    logger.info("📤 Step 3/3: Publishing to MongoDB...")
    result = publish_article(article_data)

    if result:
        logger.info(f"🎉 SUCCESS! Published: {result['slug']}")
        sys.exit(0)
    else:
        logger.error("❌ Publish failed.")
        sys.exit(1)


if __name__ == "__main__":
    run_once()
