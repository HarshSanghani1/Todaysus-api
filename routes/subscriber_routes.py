from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime
from db.mongo import mongo
from utils.sanitize import sanitize_docs

subscriber_bp = Blueprint("subscribers", __name__)

@subscriber_bp.route("/api/v1/admin/subscribers", methods=["GET"])
def list_subscribers():
    subs = list(mongo.db.subscribers.find().sort("created_at", -1))
    return jsonify(sanitize_docs(subs))

@subscriber_bp.route("/api/v1/admin/subscribers/<id>", methods=["DELETE"])
def delete(id):
    mongo.db.subscribers.delete_one({"_id": ObjectId(id)})
    return jsonify({"message": "Subscriber deleted"})
