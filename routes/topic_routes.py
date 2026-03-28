from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
from db.mongo import mongo
from slugify import slugify
from utils.sanitize import sanitize_docs

topic_bp = Blueprint("topics", __name__)

@topic_bp.route("/api/v1/admin/topics", methods=["GET"])
def admin_list():
    topics = list(mongo.db.topics.find().sort("name", 1))
    return jsonify(sanitize_docs(topics))

@topic_bp.route("/api/v1/admin/topics", methods=["POST"])
def create():
    data = request.json
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    topic = {
        "name": data["name"],
        "slug": slugify(data["name"]),
        "description": data.get("description"),
        "article_count": 0,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    mongo.db.topics.insert_one(topic)
    return jsonify({"message": "Topic created"}), 201

@topic_bp.route("/api/v1/admin/topics/<id>", methods=["PUT"])
def update(id):
    data = request.json
    mongo.db.topics.update_one(
        {"_id": ObjectId(id)},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )
    return jsonify({"message": "Topic updated"})

@topic_bp.route("/api/v1/admin/topics/<id>", methods=["DELETE"])
def delete(id):
    mongo.db.topics.delete_one({"_id": ObjectId(id)})
    return jsonify({"message": "Topic deleted"})
