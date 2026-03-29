from flask import Blueprint, jsonify, request
from bson import ObjectId
from db.mongo import mongo
from datetime import datetime
from utils.sanitize import sanitize_docs, sanitize_doc

ad_bp = Blueprint("ads", __name__)

@ad_bp.route("/api/v1/admin/ads/stats", methods=["GET"])
def get_ads_stats():
    # Calculate advanced ad metrics
    ads_cursor = mongo.db.ads.find()
    ads = list(ads_cursor)
    
    total_views = sum(ad.get("views", 0) for ad in ads)
    total_clicks = sum(ad.get("clicks", 0) for ad in ads)
    active_ads = sum(1 for ad in ads if ad.get("status") == "active")
    paused_ads = sum(1 for ad in ads if ad.get("status") == "paused")
    
    # Global CTR
    ctr = 0
    if total_views > 0:
        ctr = round((total_clicks / total_views) * 100, 2)
        
    return jsonify({
        "total_campaigns": len(ads),
        "total_views": total_views,
        "total_clicks": total_clicks,
        "ctr": ctr,
        "active": active_ads,
        "paused": paused_ads
    })

@ad_bp.route("/api/v1/admin/ads", methods=["GET"])
def get_ads():
    ads_cursor = mongo.db.ads.find().sort("created_at", -1)
    ads = list(ads_cursor)
    return jsonify(sanitize_docs(ads))

@ad_bp.route("/api/v1/admin/ads/<id>", methods=["GET"])
def get_ad(id):
    try:
        ad = mongo.db.ads.find_one({"_id": ObjectId(id)})
        if not ad:
            return jsonify({"error": "Ad not found"}), 404
        return jsonify(sanitize_doc(ad))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@ad_bp.route("/api/v1/admin/ads", methods=["POST"])
def create_ad():
    try:
        data = request.json
        if not data.get("title") or not data.get("image_url"):
            return jsonify({"error": "Title and Image URL are required"}), 400
            
        start_date = datetime.fromisoformat(data["start_date"].replace('Z', '')) if data.get("start_date") else datetime.utcnow()
        end_date = datetime.fromisoformat(data["end_date"].replace('Z', '')) if data.get("end_date") else None
        
        # Ensure pages is always a list
        pages_list = data.get("pages", ["all"])
        if not isinstance(pages_list, list):
            pages_list = [pages_list]
            
        ad_doc = {
            "title": data.get("title"),
            "image_url": data.get("image_url"),
            "redirect_url": data.get("redirect_url", ""),
            "alt_text": data.get("alt_text", ""),
            "placement": data.get("placement", "sidebar"),
            "pages": pages_list,
            "size": data.get("size", "rectangle"),
            "status": data.get("status", "paused"),
            "priority": int(data.get("priority", 10)),
            "start_date": start_date,
            "end_date": end_date,
            "views": 0,
            "clicks": 0,
            "created_at": datetime.utcnow()
        }
        
        result = mongo.db.ads.insert_one(ad_doc)
        ad_doc["_id"] = result.inserted_id
        return jsonify(sanitize_doc(ad_doc)), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@ad_bp.route("/api/v1/admin/ads/<id>", methods=["PUT"])
def update_ad(id):
    try:
        data = request.json
        
        pages_list = data.get("pages")
        if pages_list is not None and not isinstance(pages_list, list):
            pages_list = [pages_list]
            
        update_fields = {
            "title": data.get("title"),
            "image_url": data.get("image_url"),
            "redirect_url": data.get("redirect_url", ""),
            "alt_text": data.get("alt_text", ""),
            "placement": data.get("placement"),
            "pages": pages_list,
            "size": data.get("size"),
            "status": data.get("status"),
            "priority": int(data.get("priority", 10)) if data.get("priority") else None,
        }
        
        if data.get("start_date"):
            update_fields["start_date"] = datetime.fromisoformat(data["start_date"].replace('Z', ''))
        if data.get("end_date"):
            update_fields["end_date"] = datetime.fromisoformat(data["end_date"].replace('Z', ''))

        # Clean out None updates
        update_fields = {k: v for k, v in update_fields.items() if v is not None}
        
        result = mongo.db.ads.update_one(
            {"_id": ObjectId(id)},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            return jsonify({"error": "Ad not found"}), 404
            
        return jsonify({"message": "Ad updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@ad_bp.route("/api/v1/admin/ads/<id>", methods=["DELETE"])
def delete_ad(id):
    try:
        result = mongo.db.ads.delete_one({"_id": ObjectId(id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Ad not found"}), 404
        return jsonify({"message": "Ad deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
