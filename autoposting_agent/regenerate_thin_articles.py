import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Setup paths so we can import from the app
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

from autoposting_agent.config import MONGO_URI
from autoposting_agent.article_generator import generate_article
from autoposting_agent.publisher import _get_db, ensure_topics_exist, get_internal_links
from utils.seo import build_canonical_url, build_news_article_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("regenerate_articles")

def main():
    db = _get_db()
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    
    # Find all auto-generated articles in the last 5 days
    query = {
        "auto_generated": True,
        "created_at": {"$gte": five_days_ago},
        "is_deleted": False
    }
    
    articles = list(db.articles.find(query).sort("created_at", -1))
    logger.info(f"Found {len(articles)} auto-generated articles from the last 5 days.")
    
    updated_urls = []
    
    for article in articles:
        logger.info(f"--- Processing: {article.get('title')} ---")
        
        # Check if it needs regeneration (thin content, empty headings, or boilerplate, or missing faqs for GEO)
        content_html = article.get("content_html", "")
        word_count = len(content_html.split())
        needs_fix = False
        
        if word_count < 600:
            logger.info("Reason: Thin content (under 600 words)")
            needs_fix = True
        elif "<h3>Related News:" in content_html or "What Americans Need to Know" in article.get("title", ""):
            logger.info("Reason: Contains old boilerplate/padding")
            needs_fix = True
        elif not article.get("faqs") or not article.get("key_points"):
            logger.info("Reason: Missing GEO fields (faqs/key_points)")
            needs_fix = True
            
        if not needs_fix:
            logger.info("Article looks good, skipping.")
            continue
            
        # Re-generate using the existing content as the "source"
        search_result_mock = {
            "title": article.get("source_title") or article.get("title").replace(" — What Americans Need to Know", ""),
            "snippet": article.get("excerpt", ""),
            "search_topic": "news", # fallback
            "source_text": content_html,
            "url": article.get("source_url", "")
        }
        
        # Extract topics to get internal links
        article_topics = article.get("topics", [])
        ensure_topics_exist(article_topics)
        internal_links = get_internal_links(article_topics, category=article.get("category"), limit=8)
        
        logger.info("Calling LLM to regenerate...")
        new_data = generate_article(search_result_mock, internal_links)
        
        if not new_data:
            logger.error("Failed to regenerate article.")
            continue
            
        # Update DB document
        update_fields = {
            "title": new_data.get("title", article["title"]),
            "excerpt": new_data.get("excerpt", article.get("excerpt")),
            "content_html": new_data.get("content_html", content_html),
            "seo_title": new_data.get("seo_title", article.get("seo_title")),
            "seo_description": new_data.get("seo_description", article.get("seo_description")),
            "quality_score": new_data.get("quality_score", article.get("quality_score")),
            "faqs": new_data.get("faqs", []),
            "key_points": new_data.get("key_points", []),
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Re-build structured data
        temp_article = {**article, **update_fields}
        update_fields["structured_data"] = build_news_article_schema(temp_article, temp_article.get("canonical_url"))
        
        db.articles.update_one({"_id": article["_id"]}, {"$set": update_fields})
        
        url = temp_article.get("canonical_url")
        if url:
            updated_urls.append(url)
            
        logger.info(f"✅ Successfully updated: {update_fields['title']}")
        
    logger.info("=== REGENERATION COMPLETE ===")
    logger.info(f"Total updated: {len(updated_urls)}")
    print("\n--- URLs to submit to Google Search Console ---")
    for u in updated_urls:
        print(u)

if __name__ == "__main__":
    main()
