from datetime import datetime
from dateutil import parser
from slugify import slugify
import math
from utils.seo import build_canonical_url, build_news_article_schema

def parse_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        return date_val
    try:
        return parser.parse(date_val)
    except:
        return datetime.utcnow()


def calculate_reading_time(content_html):
    if not content_html:
        return 1
    words = len(content_html.split())
    return max(1, math.ceil(words / 200))


def create_article(data):
    content = data.get("content_html", "")
    now = datetime.utcnow()
    published_at = (
        parse_date(data.get("published_at"))
        if data.get("published_at")
        else now if data.get("status") == "published"
        else None
    )

    article = {
        "title": data["title"],
        "slug": slugify(data["title"]),

        "excerpt": data.get("excerpt"),
        "content_html": content,

        # Images
        "featured_image": data.get("featured_image"),
        "image_caption": data.get("image_caption"),

        # Editorial
        "type": data.get("type", "news"),   # news | analysis | explainer | opinion
        "status": data.get("status", "draft"),

        # SEO
        "seo_title": data.get("seo_title", data["title"]),
        "seo_description": data.get("seo_description", data.get("excerpt")),

        # Relations (embedded – Mongo friendly)
        "author": data["author"],
        "category": data["category"],
        "topics": data.get("topics", []),

        # Flags
        "is_featured": data.get("is_featured", False),
        "has_update": False,
        "update_note": None,

        # Metrics
        "view_count": 0,
        "reading_time": calculate_reading_time(content),

        # Dates
        "published_at": published_at,

        "created_at": now,
        "updated_at": now,

        "is_deleted": False
    }

    article["canonical_url"] = data.get("canonical_url") or build_canonical_url(article)
    article["structured_data"] = data.get("structured_data") or build_news_article_schema(
        article,
        article["canonical_url"],
    )
    return article
