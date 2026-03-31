import os
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

def run_test():
    api_key = os.environ.get('BING_WEBMASTER_API_KEY') or os.environ.get('BING_API_KEY')
    if not api_key:
        print("ERROR: No BING_WEBMASTER_API_KEY found in .env!")
        return

    print(f"Key found: {api_key[:8]}...{api_key[-4:]} (length: {len(api_key)})")

    # Test 1: Try to get sites list to verify key is valid
    print("\n--- Test 1: Verify key by listing sites ---")
    verify_url = f"https://ssl.bing.com/webmaster/api.svc/json/GetUserSites?apikey={api_key}"
    r = requests.get(verify_url)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")

    # Test 2: Try URL submission
    print("\n--- Test 2: Submit one URL ---")
    test_url = "https://www.todaysus.com/technology/us-faces-urgent-need-for-massive-ai-workforce-expansion"
    site_url = f"{urlparse(test_url).scheme}://{urlparse(test_url).netloc}"
    
    endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={api_key}"
    payload = {
        "siteUrl": site_url,
        "urlList": [test_url]
    }
    print(f"siteUrl: {site_url}")
    r2 = requests.post(endpoint, json=payload, headers={'Content-Type': 'application/json; charset=utf-8'})
    print(f"Status: {r2.status_code}")
    print(f"Response: {r2.text}")

if __name__ == "__main__":
    run_test()
