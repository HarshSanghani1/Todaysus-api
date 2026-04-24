"""SEO helpers shared by admin APIs and the autoposting agent."""
import os
from datetime import datetime


SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://todaysus.com").rstrip("/")
SITE_NAME = "TodaysUS"


def get_site_base_url() -> str:
    return os.getenv("SITE_BASE_URL", SITE_BASE_URL).rstrip("/")


def build_article_path(article: dict) -> str:
    category = article.get("category") or {}
    category_slug = category.get("slug") or article.get("category_slug") or "news"
    slug = article.get("slug") or ""
    return f"/{category_slug}/{slug}"


def build_canonical_url(article: dict) -> str:
    return f"{get_site_base_url()}{build_article_path(article)}"


def enrich_article_seo(article: dict | None) -> dict | None:
    """Add canonical URL and NewsArticle JSON-LD to an article dict."""
    if not article:
        return article

    canonical_url = article.get("canonical_url") or build_canonical_url(article)
    article["canonical_url"] = canonical_url
    article["structured_data"] = build_news_article_schema(article, canonical_url)
    return article


def build_news_article_schema(article: dict, canonical_url: str | None = None) -> dict:
    canonical_url = canonical_url or build_canonical_url(article)
    author = article.get("author") or {}
    category = article.get("category") or {}
    topics = article.get("topics") or []
    image_url = article.get("featured_image")

    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url,
        },
        "url": canonical_url,
        "headline": article.get("seo_title") or article.get("title", ""),
        "description": article.get("seo_description") or article.get("excerpt", ""),
        "datePublished": _iso(article.get("published_at") or article.get("created_at")),
        "dateModified": _iso(article.get("updated_at") or article.get("published_at")),
        "author": {
            "@type": "Person",
            "name": author.get("name", "TodaysUS Staff"),
            "url": f"{get_site_base_url()}/authors/{author.get('slug')}" if author.get("slug") else get_site_base_url(),
        },
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": get_site_base_url(),
        },
        "articleSection": category.get("name") or category.get("slug") or "News",
        "keywords": [topic.get("name", "") for topic in topics if isinstance(topic, dict) and topic.get("name")],
    }

    if image_url:
        schema["image"] = [image_url]

    return schema


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    return str(value)
