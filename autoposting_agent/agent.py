"""
Main Agent — Orchestrates the autoposting pipeline.

Flow:
  1. Search the web for a trending topic
  2. Generate a substantial article via NVIDIA LLM
  3. Publish it to MongoDB
  4. Repeat every 15 minutes via APScheduler

Usage:
  python -m autoposting_agent.agent
"""
import sys
import os
import logging
import signal
from datetime import datetime

from dotenv import load_dotenv

# Load .env from autoposting_agent dir first, then root
_agent_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_agent_dir, ".env"))
load_dotenv()  # also try root .env as fallback

from apscheduler.schedulers.blocking import BlockingScheduler

from autoposting_agent.config import POST_INTERVAL_MINUTES
from autoposting_agent.web_searcher import search_trending_topic
from autoposting_agent.article_generator import MIN_PUBLISH_WORDS, generate_article
from autoposting_agent.publisher import publish_article, is_duplicate, get_internal_links

# ── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-35s │ %(levelname)-5s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "agent.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("autoposting_agent")

# Stats
_stats = {"total_attempts": 0, "published": 0, "failed": 0, "duplicates": 0}


def run_pipeline():
    """
    Execute one cycle of the autoposting pipeline:
    Search → Generate → Publish
    """
    _stats["total_attempts"] += 1
    cycle = _stats["total_attempts"]

    logger.info("=" * 70)
    logger.info(f"🚀 CYCLE #{cycle} started at {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 70)

    # ── Step 1: Search ──────────────────────────────────────────────────
    logger.info("📡 Step 1/3: Searching for trending topics...")
    search_result = search_trending_topic()

    if not search_result or not search_result.get("title"):
        logger.error("❌ No search results found. Skipping cycle.")
        _stats["failed"] += 1
        return

    logger.info(f"   Topic: {search_result['title']}")
    logger.info(f"   Context: {search_result.get('snippet', '')[:100]}...")
    logger.info(f"   Source URL: {search_result.get('source_url', '')}")
    logger.info(f"   Source words: {search_result.get('source_word_count', 0)}")

    # ── Step 2: Fetch internal link candidates from DB ────────────────────
    # We use lightweight topic slugs from the search term to seed the query.
    # The full internal-link resolution happens inside get_internal_links().
    seed_topics = [
        {"name": w, "slug": w.lower().replace(" ", "-")}
        for w in search_result.get("search_topic", "").split()
        if len(w) > 3
    ][:5]
    internal_links = get_internal_links(seed_topics, limit=8)

    # ── Step 3: Generate ────────────────────────────────────────────────
    logger.info("🤖 Step 2/3: Generating article via NVIDIA API...")
    article_data = generate_article(search_result, internal_links=internal_links)

    if not article_data:
        logger.error("❌ Article generation failed. Skipping cycle.")
        _stats["failed"] += 1
        return

    word_count = int(
        article_data.get("word_count")
        or len(article_data.get("content_html", "").split())
    )
    if word_count < MIN_PUBLISH_WORDS:
        logger.error(
            "❌ Article below publishable length (%s words; minimum %s). Skipping cycle.",
            word_count,
            MIN_PUBLISH_WORDS,
        )
        _stats["failed"] += 1
        return

    # Quick duplicate check before publish
    if is_duplicate(article_data["title"]):
        logger.warning(f"⚠️  Duplicate detected pre-publish: {article_data['title']}")
        _stats["duplicates"] += 1
        return

    content_len = len(article_data.get("content_html", ""))
    logger.info(f"   Title ({len(article_data['title'])} chars): {article_data['title']}")
    logger.info(f"   Category: {article_data.get('category', {}).get('name', 'Unknown')}")
    logger.info(f"   Structure: {article_data.get('article_structure', 'unknown')}")
    logger.info(f"   Quality score: {article_data.get('quality_score', 0)}/10 | Featured: {article_data.get('is_featured', False)}")
    logger.info(f"   Internal links injected: {len(internal_links)}")
    logger.info(f"   Content length: {content_len} chars, ~{word_count} words")

    # ── Step 4: Publish ─────────────────────────────────────────────────
    logger.info("📤 Step 3/3: Publishing to MongoDB...")
    result = publish_article(article_data)

    if result:
        _stats["published"] += 1
        logger.info(f"🎉 SUCCESS! Article published: {result['slug']}")
    else:
        _stats["failed"] += 1
        logger.error("❌ Publishing failed.")

    # Print stats
    logger.info(
        f"📊 Stats: {_stats['published']} published | "
        f"{_stats['failed']} failed | "
        f"{_stats['duplicates']} duplicates | "
        f"{_stats['total_attempts']} total cycles"
    )
    logger.info(f"⏰ Next cycle in {POST_INTERVAL_MINUTES} minutes...")


def main():
    """Entry point — runs the agent with APScheduler."""
    logger.info("=" * 70)
    logger.info("  🤖 TodaysUS AutoPosting Agent v1.0")
    logger.info(f"  ⏱️  Interval: Every {POST_INTERVAL_MINUTES} minutes")
    logger.info(f"  🕐 Started at: {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 70)

    # Verify NVIDIA API key
    from autoposting_agent.config import NVIDIA_API_KEY
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY not found in environment! Set it in .env")
        logger.error("   Add: NVIDIA_API_KEY=nvapi-xxxxxxxxxxxx")
        sys.exit(1)

    # Run immediately on start
    logger.info("🏁 Running first cycle immediately...")
    run_pipeline()

    # Schedule recurring runs
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        minutes=POST_INTERVAL_MINUTES,
        id="autopost_job",
        name="AutoPost Article",
        max_instances=1,
        coalesce=True,
    )

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("🛑 Shutting down agent...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info(f"⏰ Scheduler started — posting every {POST_INTERVAL_MINUTES} minutes")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Agent stopped.")


if __name__ == "__main__":
    main()
