from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash
from db.mongo import mongo
from datetime import datetime

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/v1/admin/auth/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400
        
    user = mongo.db.users.find_one({"username": username})
    
    if not user or not check_password_hash(user["password"], password):
        # Prevent timing attacks somewhat, log failures conceptually
        return jsonify({"error": "Invalid credentials"}), 401
        
    session["user_id"] = str(user["_id"])
    session["username"] = user["username"]
    session["role"] = user["role"]
    
    # Optional login tracking
    mongo.db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )

    return jsonify({"message": "Successfully logged in", "user": {"username": user["username"], "role": user["role"]}})

@auth_bp.route("/api/v1/admin/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Successfully logged out"})
