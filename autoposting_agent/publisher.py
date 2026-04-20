"""
Publisher — inserts generated articles directly into MongoDB.
Uses the same article model as the main Flask app.
"""
import os
import logging
from datetime import datetime

from pymongo import MongoClient
from slugify import slugify

from autoposting_agent.config import MONGO_URI, AUTHORS

logger = logging.getLogger("autoposting_agent.publisher")

# Direct MongoDB connection (no Flask context needed)
_client = None
_db = None


def _get_db():
    """Lazy-init MongoDB connection."""
    global _client, _db
    if _db is None:
        uri = MONGO_URI or os.getenv("MONGO_URI", "")
        if not uri:
            raise RuntimeError("MONGO_URI is not configured!")
        _client = MongoClient(uri)
        # Extract DB name from URI (last segment before query params)
        db_name = uri.split("/")[-1].split("?")[0] or "todaysus"
        _db = _client[db_name]
        logger.info(f"📦 Connected to MongoDB: {db_name}")
    return _db


def _calculate_reading_time(content_html: str) -> int:
    """Estimate reading time in minutes."""
    if not content_html:
        return 1
    words = len(content_html.split())
    import math
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
            "seo_description": article_data.get("seo_description", article_data.get("excerpt", "")),

            # Relations
            "author": _get_next_author(),
            "category": article_data.get("category", {
                "id": "696ca7bdecbd8aee584d42a8",
                "name": "World",
                "slug": "world"
            }),
            "topics": article_data.get("topics", []),

            # Flags
            "is_featured": False,
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

            # Tag for auto-generated content
            "auto_generated": True,
        }

        result = db.articles.insert_one(article)
        logger.info(f"✅ Published: '{title}' (slug: {slug}, id: {result.inserted_id})")

        # Sync topics
        _sync_topics(db, article.get("topics", []))

        return article

    except Exception as e:
        logger.error(f"❌ Publish failed: {e}")
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
                {"$inc": {"article_count": 1}, "$set": {"updated_at": datetime.utcnow()}}
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
