from flask import Blueprint, jsonify
from db.mongo import mongo

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/api/v1/admin/dashboard/stats", methods=["GET"])
def stats():
    articles_total = mongo.db.articles.count_documents({"is_deleted": False})
    articles_pub = mongo.db.articles.count_documents({"status": "published", "is_deleted": False})
    articles_draft = mongo.db.articles.count_documents({"status": "draft", "is_deleted": False})
    categories = mongo.db.categories.count_documents({})
    topics = mongo.db.topics.count_documents({})
    authors = mongo.db.authors.count_documents({})
    subscribers = mongo.db.subscribers.count_documents({})
    
    # Total views
    pipeline = [
        {"$match": {"is_deleted": False}},
        {"$group": {"_id": None, "total_views": {"$sum": "$view_count"}}}
    ]
    views_result = list(mongo.db.articles.aggregate(pipeline))
    total_views = views_result[0]["total_views"] if views_result else 0

    return jsonify({
        "articles_total": articles_total,
        "articles_published": articles_pub,
        "articles_draft": articles_draft,
        "categories": categories,
        "topics": topics,
        "authors": authors,
        "subscribers": subscribers,
        "total_views": total_views
    })
