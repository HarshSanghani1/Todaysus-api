from datetime import datetime
from slugify import slugify

def create_topic(name):
    return {
        "name": name,
        "slug": slugify(name),
        "description": None,
        "article_count": 1,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
