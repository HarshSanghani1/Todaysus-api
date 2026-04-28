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
from utils.seo import build_canonical_url, build_news_article_schema, get_site_base_url

logger = logging.getLogger("autoposting_agent.publisher")

# ── MongoDB lazy connection ──────────────────────────────────────────────────
_client = None
_db = None

SITE_BASE_URL = get_site_base_url()


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


def ensure_topics_exist(article_topics: list[dict]) -> None:
    """
    Upsert lightweight topic stubs into the DB for every seed keyword BEFORE
    the internal-link lookup runs.  This ensures the relevance search always
    finds topically-correct candidates even when the topic is brand-new.

    Stubs are created with article_count=0 so they don't pollute the popular-
    topic ranking until a real article is published against them.
    """
    if not article_topics:
        return
    try:
        db = _get_db()
        now = datetime.utcnow()
        for t in article_topics:
            slug = t.get("slug", "")
            name = t.get("name", slug)
            if not slug:
                continue
            db.topics.update_one(
                {"slug": slug},
                {
                    "$setOnInsert": {
                        "name": name,
                        "slug": slug,
                        "description": None,
                        "article_count": 0,
                        "is_active": True,
                        "created_at": now,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
        logger.info(f"🏷️  Ensured {len(article_topics)} topic stub(s) exist in DB")
    except Exception as e:
        logger.warning(f"⚠️  Could not ensure topic stubs: {e}")


def get_internal_links(
    article_topics: list[dict],
    category: dict | None = None,
    limit: int = 8,
) -> list[dict]:
    """
    Fetch relevant internal link candidates for the article.

    Strategy (in priority order):
      1. Topics in the DB that share keywords with the article's own topics
         (scored by keyword overlap + article_count popularity).
      2. If fewer than 2 topically-relevant links are found, pad with the
         article's category page link so the LLM always has *something*
         meaningful to link to — never random unrelated topics.

    Returns list of {"name": str, "slug": str, "url": str}.
    """
    try:
        db = _get_db()
        own_slugs = {t.get("slug", "") for t in article_topics}

        # Build keyword hints from the article's seed topics
        keyword_hints: list[str] = []
        for t in article_topics:
            keyword_hints.extend(t.get("name", "").lower().split())
        keyword_set = set(keyword_hints)

        # Fetch up to 60 active topics sorted by popularity
        candidates = list(
            db.topics.find(
                {"is_active": True, "article_count": {"$gte": 1}},
                {"name": 1, "slug": 1, "article_count": 1},
            )
            .sort("article_count", -1)
            .limit(60)
        )

        # Score: ONLY boost topics whose name genuinely overlaps with article keywords.
        # A zero-overlap topic scores only its article_count which is deprioritised
        # far below any topic with even 1 keyword match.
        def relevance_score(topic):
            name_words = set(topic.get("name", "").lower().split())
            overlap = len(name_words & keyword_set)
            if overlap == 0:
                return topic.get("article_count", 0)          # low base score
            return (overlap * 100) + topic.get("article_count", 0)  # high score

        # Filter out the article's own topics, rank by relevance
        candidates = [c for c in candidates if c.get("slug", "") not in own_slugs]
        candidates.sort(key=relevance_score, reverse=True)

        # Only keep candidates that have at least 1 keyword overlap with the article
        relevant = [c for c in candidates if relevance_score(c) >= 100]
        fallback_pool = [c for c in candidates if relevance_score(c) < 100]

        # Build links from relevant candidates (up to limit)
        links: list[dict] = []
        for c in relevant[:limit]:
            slug = c.get("slug", "")
            name = c.get("name", slug)
            links.append({"name": name, "slug": slug, "url": f"{SITE_BASE_URL}/topics/{slug}"})

        # If we have fewer than 2 relevant topic links, add the category page link
        # so the LLM always has at least one meaningful, on-topic internal link.
        if len(links) < 2 and category:
            cat_slug = category.get("slug", "")
            cat_name = category.get("name", cat_slug.title())
            if cat_slug:
                links.insert(0, {
                    "name": f"{cat_name} News",
                    "slug": cat_slug,
                    "url": f"{SITE_BASE_URL}/category/{cat_slug}",
                })
                logger.info(f"📂 Added category fallback link: /category/{cat_slug}")

        # If still short, pad with a few popular-but-different topics (max 2)
        # so the LLM has options, but label them clearly as low-priority.
        if len(links) < 2:
            for c in fallback_pool[:2]:
                slug = c.get("slug", "")
                name = c.get("name", slug)
                links.append({"name": name, "slug": slug, "url": f"{SITE_BASE_URL}/topics/{slug}"})

        logger.info(f"🔗 Found {len(links)} internal link candidate(s) ({len(relevant)} topic match(es))")
        return links[:limit]

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
        now = datetime.utcnow()

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
            "published_at": now,
            "created_at": now,
            "updated_at": now,

            # Soft delete
            "is_deleted": False,

            # Auto-generation metadata
            "auto_generated": True,
            "quality_score": quality_score,
            "article_structure": article_data.get("article_structure", ""),
            "source_url": article_data.get("source_url", ""),
            "source_title": article_data.get("source_title", ""),
            "source_word_count": article_data.get("source_word_count", 0),
            "source_timestamp_utc": article_data.get("source_timestamp_utc", ""),
        }

        article["canonical_url"] = article_data.get("canonical_url") or build_canonical_url(article)
        article["structured_data"] = article_data.get("structured_data") or build_news_article_schema(
            article,
            article["canonical_url"],
        )

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
