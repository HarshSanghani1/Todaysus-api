from flask import Blueprint, jsonify, request
from bson import ObjectId
from db.mongo import mongo
from datetime import datetime
from utils.sanitize import sanitize_docs, sanitize_doc

horoscope_bp = Blueprint("horoscopes", __name__)

@horoscope_bp.route("/api/v1/admin/horoscopes", methods=["GET"])
def get_horoscopes():
    # Fetch top 100 recent by default to not overwhelm UI
    horo_cursor = mongo.db.horoscopes.find().sort("date", -1).limit(100)
    return jsonify(sanitize_docs(list(horo_cursor)))

@horoscope_bp.route("/api/v1/admin/horoscopes/<id>", methods=["GET"])
def get_horoscope(id):
    try:
        horo = mongo.db.horoscopes.find_one({"_id": ObjectId(id)})
        if not horo:
            return jsonify({"error": "Horoscope not found"}), 404
        return jsonify(sanitize_doc(horo))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@horoscope_bp.route("/api/v1/admin/horoscopes/<id>", methods=["PUT"])
def update_horoscope(id):
    try:
        data = request.json
        update_fields = {
            "date": data.get("date"),
            "period": data.get("period"),
            "sign": data.get("sign"),
            "horoscope": data.get("horoscope")
        }
        update_fields = {k: v for k, v in update_fields.items() if v is not None}
        
        result = mongo.db.horoscopes.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_fields}
        )
        if result.matched_count == 0:
            return jsonify({"error": "Horoscope not found"}), 404
            
        return jsonify({"message": "Horoscope updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@horoscope_bp.route("/api/v1/admin/horoscopes/<id>", methods=["DELETE"])
def delete_horoscope(id):
    try:
        result = mongo.db.horoscopes.delete_one({"_id": ObjectId(id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Horoscope not found"}), 404
        return jsonify({"message": "Horoscope deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@horoscope_bp.route("/api/v1/admin/horoscopes/bulk-delete", methods=["POST"])
def bulk_delete_horoscopes():
    try:
        data = request.json
        cutoff_date = data.get("cutoff_date") # e.g. '2026-03-01'
        
        if not cutoff_date:
            return jsonify({"error": "Cutoff date required in format YYYY-MM-DD"}), 400
            
        # Horoscopes use string 'date' field (e.g. '2026-03-16')
        result = mongo.db.horoscopes.delete_many({"date": {"$lt": cutoff_date}})
        
        return jsonify({"message": f"Successfully deleted {result.deleted_count} past horoscopes."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
