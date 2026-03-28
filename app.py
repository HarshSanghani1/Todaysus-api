from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime
from bson import ObjectId
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask.json.provider import DefaultJSONProvider
from config import Config
from db.mongo import mongo
from routes.article_routes import article_bp
from routes.category_routes import category_bp
from routes.topic_routes import topic_bp
from routes.author_routes import author_bp
from routes.subscriber_routes import subscriber_bp
from routes.dashboard_routes import dashboard_bp
from routes.auth_routes import auth_bp


class CustomJSONProvider(DefaultJSONProvider):
    """Serialize datetime as ISO string, ObjectId as str."""
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat() + "Z"
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-unique-todaysus-key")
app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)
app.config.from_object(Config)

mongo.init_app(app)

@app.before_request
def check_auth():
    # Allow static files and the login route
    if request.endpoint in ("login", "static", "auth.login"):
        return
    
    # Check if a public route (some API endpoints might be public, like article list)
    # The requirement is that all admin stuff is locked down.
    # Public routes in article_routes for the frontend are `/api/v1/articles`
    # Admin routes are under `/api/v1/admin/...`
    # HTML admin dashboards are everything except /login.
    
    path = request.path
    if path.startswith("/api/v1/") and not path.startswith("/api/v1/admin/"):
        return # public API
        
    if "user_id" not in session:
        # Prevent unauthorized access. Return JSON for APIs, redirect for Pages.
        if path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        else:
            return redirect(url_for("login"))


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "0"
    return response

# --- Pages ---
@app.route("/login")
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/articles")
def articles_page():
    return render_template("articles.html")

@app.route("/articles/new")
def new_article_page():
    return render_template("post_article.html")

@app.route("/articles/json")
def json_article_page():
    return render_template("post_json.html")

@app.route("/articles/<id>/edit")
def edit_article_page(id):
    return render_template("post_article.html", article_id=id)

@app.route("/categories")
def categories_page():
    return render_template("categories.html")

@app.route("/topics")
def topics_page():
    return render_template("topics.html")

@app.route("/authors")
def authors_page():
    return render_template("authors.html")

@app.route("/subscribers")
def subscribers_page():
    return render_template("subscribers.html")

# --- API Blueprints ---
app.register_blueprint(article_bp)
app.register_blueprint(category_bp)
app.register_blueprint(topic_bp)
app.register_blueprint(author_bp)
app.register_blueprint(subscriber_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(auth_bp)


if __name__ == "__main__":
    app.run(debug=True)
