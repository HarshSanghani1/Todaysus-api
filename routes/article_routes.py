from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
from db.mongo import mongo
from models.article_model import create_article
from utils.helper import sync_topics
from utils.sanitize import sanitize_doc, sanitize_docs

article_bp = Blueprint("articles", __name__)

# ---------------- ADMIN CRUD ---------------- #

@article_bp.route("/api/v1/admin/articles", methods=["POST"])
def create():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    try:
        article = create_article(data)
        mongo.db.articles.insert_one(article)
        if article.get("topics"):
            sync_topics(article["topics"])
        return jsonify({"message": "Article created", "slug": article["slug"]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@article_bp.route("/api/v1/admin/articles/<id>", methods=["PUT"])
def update(id):
    data = request.json
    update_data = {**data, "updated_at": datetime.utcnow()}
    if "content_html" in data:
        update_data["has_update"] = True
        update_data["update_note"] = data.get("update_note", "Article updated for clarity")
    mongo.db.articles.update_one(
        {"_id": ObjectId(id), "is_deleted": False},
        {"$set": update_data}
    )
    return jsonify({"message": "Article updated"})


@article_bp.route("/api/v1/admin/articles/<id>", methods=["DELETE"])
def delete(id):
    mongo.db.articles.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"is_deleted": True}}
    )
    return jsonify({"message": "Article deleted"})


@article_bp.route("/api/v1/admin/articles", methods=["GET"])
def admin_list():
    status = request.args.get("status")
    query = {"is_deleted": False}
    if status:
        query["status"] = status
    projection = {"content_html": 0} if request.args.get("full") != "true" else None
    articles = list(mongo.db.articles.find(query, projection).sort("created_at", -1))
    return jsonify(sanitize_docs(articles))


@article_bp.route("/api/v1/admin/articles/<id>", methods=["GET"])
def admin_get(id):
    article = mongo.db.articles.find_one({"_id": ObjectId(id), "is_deleted": False})
    if not article:
        return jsonify({"error": "Not found"}), 404
    return jsonify(sanitize_doc(article))


# ---------------- PUBLIC ---------------- #

@article_bp.route("/api/v1/articles", methods=["GET"])
def list_articles():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit
    query = {"status": "published", "is_deleted": False, "published_at": {"$lte": datetime.utcnow()}}
    cursor = mongo.db.articles.find(query).sort("published_at", -1).skip(skip).limit(limit)
    articles = sanitize_docs(list(cursor))
    total = mongo.db.articles.count_documents(query)
    return jsonify({"data": articles, "page": page, "limit": limit, "total": total})


@article_bp.route("/api/v1/articles/<slug>", methods=["GET"])
def single_article(slug):
    article = mongo.db.articles.find_one_and_update(
        {"slug": slug, "status": "published", "is_deleted": False},
        {"$inc": {"view_count": 1}, "$set": {"updated_at": datetime.utcnow()}},
        return_document=True
    )
    if not article:
        return jsonify({"error": "Not found"}), 404
    return jsonify(sanitize_doc(article))


@article_bp.route("/api/v1/articles/latest")
def latest():
    query = {"status": "published", "is_deleted": False, "published_at": {"$lte": datetime.utcnow()}}
    articles = list(mongo.db.articles.find(query).sort("published_at", -1).limit(10))
    return jsonify(sanitize_docs(articles))


@article_bp.route("/api/v1/articles/most-read")
def most_read():
    articles = list(mongo.db.articles.find(
        {"status": "published", "is_deleted": False}
    ).sort("view_count", -1).limit(10))
    return jsonify(sanitize_docs(articles))
