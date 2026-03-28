from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
from db.mongo import mongo
from slugify import slugify
from utils.sanitize import sanitize_docs

category_bp = Blueprint("categories", __name__)

@category_bp.route("/api/v1/admin/categories", methods=["POST"])
def create():
    data = request.json
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    category = {
        "name": data["name"],
        "slug": slugify(data["name"]),
        "description": data.get("description"),
        "seo_title": data.get("seo_title", data["name"]),
        "seo_description": data.get("seo_description"),
        "order": data.get("order", 0),
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    mongo.db.categories.insert_one(category)
    return jsonify({"message": "Category created"}), 201

@category_bp.route("/api/v1/admin/categories", methods=["GET"])
def admin_list():
    categories = list(mongo.db.categories.find().sort("order", 1))
    return jsonify(sanitize_docs(categories))

@category_bp.route("/api/v1/admin/categories/<id>", methods=["PUT"])
def update(id):
    data = request.json
    mongo.db.categories.update_one(
        {"_id": ObjectId(id)},
        {"$set": {**data, "updated_at": datetime.utcnow()}}
    )
    return jsonify({"message": "Category updated"})

@category_bp.route("/api/v1/admin/categories/<id>", methods=["DELETE"])
def delete(id):
    mongo.db.categories.delete_one({"_id": ObjectId(id)})
    return jsonify({"message": "Category deleted"})
