from datetime import datetime
from slugify import slugify
import math

def calculate_reading_time(content_html):
    if not content_html:
        return 1
    words = len(content_html.split())
    return max(1, math.ceil(words / 200))


def create_article(data):
    content = data.get("content_html", "")

    return {
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
        # "published_at": data.get("published_at"),
        "published_at": (
            data.get("published_at")
            if data.get("published_at")
            else datetime.utcnow() if data.get("status") == "published"
            else None
        ),

        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),

        "is_deleted": False
    }
