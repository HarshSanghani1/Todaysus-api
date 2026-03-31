from flask import Blueprint, request, jsonify
import requests
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from db.mongo import mongo
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from urllib.parse import urlparse

indexing_bp = Blueprint('indexing', __name__, url_prefix='/api/v1/admin/indexing')

# --- Helpers ---

def get_google_auth_session(scopes):
    # Try reading from environment variable first (Vercel deployment)
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        try:
            creds_info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
            return AuthorizedSession(credentials)
        except Exception as e:
            print(f"Error parsing GOOGLE_CREDENTIALS env var: {str(e)}")
            return None

    # Fallback to local file
    key_path = os.path.join(os.getcwd(), 'service_account.json')
    if not os.path.exists(key_path):
        return None
    credentials = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
    return AuthorizedSession(credentials)

def fetch_and_parse_sitemap(url, visited=None):
    """Recursive sitemap parser for both urlset and sitemapindex."""
    if visited is None: visited = set()
    if url in visited: return []
    visited.add(url)
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        # Handle different namespaces common in sitemaps
        ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        urls = []
        # Check if it's a sitemap index
        sitemap_tags = root.findall('.//ns:sitemap', ns)
        if sitemap_tags:
            for s in sitemap_tags:
                loc = s.find('ns:loc', ns)
                if loc is not None:
                    urls.extend(fetch_and_parse_sitemap(loc.text.strip(), visited))
        else:
            # It's a regular urlset
            url_tags = root.findall('.//ns:url', ns)
            for u in url_tags:
                loc = u.find('ns:loc', ns)
                if loc is not None:
                    urls.append(loc.text.strip())
                    
        return list(set(urls)) # Remove duplicates
    except Exception as e:
        print(f"Error fetching sitemap {url}: {str(e)}")
        return []

# --- Routes ---

@indexing_bp.route('/bing-config', methods=['GET'])
def get_bing_config():
    key = os.environ.get('INDEXNOW_KEY') or os.environ.get('BING_API_KEY')
    return jsonify({"key": key})

@indexing_bp.route('/fetch-sitemap', methods=['POST'])
def fetch_sitemap_route():
    sitemap_url = request.json.get('sitemap_url')
    if not sitemap_url:
        return jsonify({"success": False, "message": "Sitemap URL is required"}), 400
    
    urls = fetch_and_parse_sitemap(sitemap_url)
    return jsonify({
        "success": True,
        "count": len(urls),
        "urls": urls
    })

@indexing_bp.route('/submit', methods=['POST'])
def submit_urls():
    data = request.json
    urls = data.get('urls', [])
    targets = data.get('targets', [])  # ['google', 'bing']
    action = data.get('action', 'URL_UPDATED')
    
    if not urls:
        return jsonify({"success": False, "message": "No URLs provided"}), 400
    
    results = {
        "google": {"success": [], "failed": []},
        "bing": {"success": [], "failed": []}
    }
    
    # --- Google Submission ---
    if 'google' in targets:
        session = get_google_auth_session(['https://www.googleapis.com/auth/indexing'])
        if not session:
            results['google']['failed'].append("Missing GOOGLE_CREDENTIALS env var or service_account.json in root!")
        else:
            endpoint = 'https://indexing.googleapis.com/v3/urlNotifications:publish'
            for url in urls:
                try:
                    payload = {"url": url, "type": action}
                    response = session.post(endpoint, json=payload)
                    if response.status_code == 200:
                        results['google']['success'].append(url)
                    else:
                        results['google']['failed'].append({"url": url, "error": response.json()})
                except Exception as e:
                    results['google']['failed'].append({"url": url, "error": str(e)})

    # --- IndexNow (Bing/Edge) Submission ---
    if 'bing' in targets:
        api_key = os.environ.get('INDEXNOW_KEY') or os.environ.get('BING_API_KEY')
        
        if not api_key:
            results['bing']['failed'].append("INDEXNOW_KEY is not configured in .env")
        else:
            try:
                # Always use the site's own domain for the keyLocation
                # This must match the domain of the URLs being submitted
                parsed_uri = urlparse(urls[0])
                host_name = parsed_uri.netloc  # e.g. todaysus.com or www.todaysus.com
                scheme = parsed_uri.scheme     # https

                payload = {
                    "host": host_name,
                    "key": api_key,
                    "keyLocation": f"{scheme}://{host_name}/{api_key}.txt",
                    "urlList": urls
                }
                
                endpoint = 'https://api.indexnow.org/indexnow'
                response = requests.post(endpoint, json=payload, headers={'Content-Type': 'application/json; charset=utf-8'})
                
                if response.status_code in [200, 202]:
                    results['bing']['success'] = urls
                else:
                    results['bing']['failed'].append(f"Status {response.status_code}: {response.text}")
            except Exception as e:
                results['bing']['failed'].append(f"Error: {str(e)}")
    
    # Save to history
    try:
        mongo.db.indexing_history.insert_one({
            "timestamp": datetime.utcnow(),
            "urls": urls,
            "targets": targets,
            "google_success": len(results['google']['success']),
            "google_failed": len(results['google']['failed']),
            "bing_success": len(results['bing']['success']),
            "bing_failed": len(results['bing']['failed'])
        })
    except: pass

    return jsonify({
        "success": True,
        "message": "Indexing request processed",
        "results": results
    })

@indexing_bp.route('/history', methods=['GET'])
def get_history():
    history = list(mongo.db.indexing_history.find().sort("timestamp", -1).limit(10))
    for h in history:
        h['_id'] = str(h['_id'])
    return jsonify(history)
