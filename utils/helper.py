from datetime import datetime

from flask import abort, render_template
from db.mongo import mongo
from models.topic_model import create_topic
from dateutil import parser


def sync_topics(topics):
    for t in topics:
        slug = t["slug"]

        existing = mongo.db.topics.find_one({"slug": slug})

        if existing:
            mongo.db.topics.update_one(
                {"_id": existing["_id"]},
                {
                    "$inc": {"article_count": 1},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )
        else:
            mongo.db.topics.insert_one(
                create_topic(t["name"])
            )



def normalize_articles(items):
    """
    Fix dates + ids so templates never crash
    """
    for a in items:
        if isinstance(a.get("published_at"), str):
            a["published_at"] = parser.parse(a["published_at"])

        if isinstance(a.get("created_at"), str):
            a["created_at"] = parser.parse(a["created_at"])

        if not a.get("published_at"):
            a["published_at"] = a.get("created_at")

        a["_id"] = str(a["_id"])
    return items


def render_static_page(slug, template):
    page = mongo.db.pages.find_one({
        "slug": slug,
        "is_active": True
    })

    if not page:
        abort(404)

    return render_template(
        template,
        page=page,
        current_year=datetime.utcnow().year
    )
