from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
from db.mongo import mongo
from slugify import slugify
from utils.sanitize import sanitize_docs

author_bp = Blueprint("authors", __name__)

@author_bp.route("/api/v1/admin/authors", methods=["GET"])
def list_authors():
    authors = list(mongo.db.authors.find())
    return jsonify(sanitize_docs(authors))

@author_bp.route("/api/v1/admin/authors", methods=["POST"])
def create():
    data = request.json
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    slug = slugify(data["name"])
    if mongo.db.authors.find_one({"slug": slug}):
        return jsonify({"error": "Author already exists"}), 409
    author = {
        "name": data["name"],
        "slug": slug,
        "display_name": data.get("display_name", data["name"]),
        "role": data.get("role", "contributor"),
        "type": data.get("type", "human"),
        "bio": data.get("bio"),
        "short_bio": data.get("short_bio"),
        "email": data.get("email"),
        "photo": data.get("photo"),
        "social": data.get("social", {}),
        "is_active": True,
        "is_verified": False,
        "is_public": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    mongo.db.authors.insert_one(author)
    return jsonify({"message": "Author created", "slug": slug}), 201

@author_bp.route("/api/v1/admin/authors/<slug>", methods=["PUT"])
def update(slug):
    data = request.json
    result = mongo.db.authors.update_one(
        {"slug": slug},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Author not found"}), 404
    return jsonify({"message": "Author updated"})

@author_bp.route("/api/v1/admin/authors/<slug>", methods=["DELETE"])
def delete(slug):
    result = mongo.db.authors.delete_one({"slug": slug})
    if result.deleted_count == 0:
        return jsonify({"error": "Author not found"}), 404
    return jsonify({"message": "Author deleted"})
