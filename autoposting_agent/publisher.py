"""
Publisher — inserts generated articles directly into MongoDB.
Uses the same article model as the main Flask app.

Changes:
  • get_internal_links()  — fetches up to 8 active topics from DB,
                            building /topics/<slug> URLs for use as internal links.
  • publish_article()     — honours is_featured from article_data,
                            stores quality_score and article_structure metadata.
"""
import os
import logging
import math
from datetime import datetime

from pymongo import MongoClient
from slugify import slugify

from autoposting_agent.config import MONGO_URI, AUTHORS

logger = logging.getLogger("autoposting_agent.publisher")

# ── MongoDB lazy connection ──────────────────────────────────────────────────
_client = None
_db = None

SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://todaysus.com")


def _get_db():
    """Lazy-init MongoDB connection."""
    global _client, _db
    if _db is None:
        uri = MONGO_URI or os.getenv("MONGO_URI", "")
        if not uri:
            raise RuntimeError("MONGO_URI is not configured!")
        _client = MongoClient(uri)
        db_name = uri.split("/")[-1].split("?")[0] or "todaysus"
        _db = _client[db_name]
        logger.info(f"📦 Connected to MongoDB: {db_name}")
    return _db


def _calculate_reading_time(content_html: str) -> int:
    """Estimate reading time in minutes (200 wpm)."""
    if not content_html:
        return 1
    words = len(content_html.split())
    return max(1, math.ceil(words / 200))


def _get_next_author() -> dict:
    """
    Alternate authors one-by-one.
    Tracks which author was used last via a counter in MongoDB.
    """
    db = _get_db()
    counter = db.agent_state.find_one_and_update(
        {"_id": "author_counter"},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True,
    )
    idx = counter["count"] % len(AUTHORS)
    author = AUTHORS[idx]
    logger.info(f"👤 Author: {author['name']}")
    return author


def is_duplicate(title: str) -> bool:
    """Check if an article with a similar title/slug already exists."""
    db = _get_db()
    slug = slugify(title)
    existing = db.articles.find_one({"slug": slug, "is_deleted": False})
    return existing is not None


def get_internal_links(article_topics: list[dict], limit: int = 8) -> list[dict]:
    """
    Fetch active topics from the DB that differ from the article's own topics.
    Returns list of {"name": str, "slug": str, "url": str} ready for the LLM.

    Preference order:
      1. Topics that share keywords with article topics (most relevant)
      2. High article_count topics (popular topics = link authority)
    """
    try:
        db = _get_db()
        own_slugs = {t.get("slug", "") for t in article_topics}

        # Prefer topics related by keyword to the article's own topic names
        keyword_hints = []
        for t in article_topics:
            name = t.get("name", "")
            keyword_hints.extend(name.lower().split())

        # Fetch up to 40 active topics sorted by popularity
        candidates = list(
            db.topics.find(
                {"is_active": True, "article_count": {"$gte": 1}},
                {"name": 1, "slug": 1, "article_count": 1},
            )
            .sort("article_count", -1)
            .limit(40)
        )

        # Score: boost ones whose name shares words with article topics
        def relevance_score(topic):
            name_words = set(topic.get("name", "").lower().split())
            overlap = len(name_words & set(keyword_hints))
            return (overlap * 10) + topic.get("article_count", 0)

        # Filter out own topics, sort by relevance
        candidates = [c for c in candidates if c.get("slug", "") not in own_slugs]
        candidates.sort(key=relevance_score, reverse=True)

        links = []
        for c in candidates[:limit]:
            slug = c.get("slug", "")
            name = c.get("name", slug)
            links.append({
                "name": name,
                "slug": slug,
                "url": f"{SITE_BASE_URL}/topics/{slug}",
            })

        logger.info(f"🔗 Found {len(links)} internal link candidates from DB topics")
        return links

    except Exception as e:
        logger.warning(f"⚠️  Could not fetch internal links from DB: {e}")
        return []


def publish_article(article_data: dict) -> dict | None:
    """
    Insert the generated article into MongoDB.
    Uses the same schema as models/article_model.py.
    Returns the inserted article dict or None on failure.
    """
    try:
        db = _get_db()

        title = article_data["title"]
        slug = slugify(title)

        # Check for duplicates
        if is_duplicate(title):
            logger.warning(f"⚠️  Duplicate article skipped: {title}")
            return None

        content_html = article_data.get("content_html", "")

        # Determine featured status — trust the generator's decision
        is_featured = bool(article_data.get("is_featured", False))
        quality_score = int(article_data.get("quality_score", 0))

        article = {
            "title": title,
            "slug": slug,
            "excerpt": article_data.get("excerpt", ""),
            "content_html": content_html,

            # Images
            "featured_image": None,
            "image_caption": None,

            # Editorial
            "type": article_data.get("type", "news"),
            "status": "published",

            # SEO
            "seo_title": article_data.get("seo_title", title),
            "seo_description": article_data.get(
                "seo_description", article_data.get("excerpt", "")
            ),

            # Relations
            "author": _get_next_author(),
            "category": article_data.get("category", {
                "id": "696ca7bdecbd8aee584d42a8",
                "name": "World",
                "slug": "world",
            }),
            "topics": article_data.get("topics", []),

            # Flags
            "is_featured": is_featured,
            "has_update": False,
            "update_note": None,

            # Metrics
            "view_count": 0,
            "reading_time": _calculate_reading_time(content_html),

            # Dates
            "published_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),

            # Soft delete
            "is_deleted": False,

            # Auto-generation metadata
            "auto_generated": True,
            "quality_score": quality_score,
            "article_structure": article_data.get("article_structure", ""),
        }

        result = db.articles.insert_one(article)
        featured_tag = "⭐ FEATURED" if is_featured else ""
        logger.info(
            f"✅ Published {featured_tag}: '{title}' "
            f"(slug: {slug}, Q:{quality_score}/10, id: {result.inserted_id})"
        )

        # Sync topics to the topics collection
        _sync_topics(db, article.get("topics", []))

        return article

    except Exception as e:
        logger.error(f"❌ Publish failed: {e}", exc_info=True)
        return None


def _sync_topics(db, topics: list):
    """Sync topics to the topics collection (mirrors utils/helper.py)."""
    for t in topics:
        slug = t.get("slug", "")
        if not slug:
            continue
        existing = db.topics.find_one({"slug": slug})
        if existing:
            db.topics.update_one(
                {"_id": existing["_id"]},
                {"$inc": {"article_count": 1}, "$set": {"updated_at": datetime.utcnow()}},
            )
        else:
            db.topics.insert_one({
                "name": t.get("name", slug),
                "slug": slug,
                "description": None,
                "article_count": 1,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
