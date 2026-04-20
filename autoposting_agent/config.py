"""
Configuration for the autoposting agent.
"""
import os

# ── NVIDIA API ──────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"  # powerful, fast, free-tier friendly

# ── MongoDB ─────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "")

# ── Scheduling ──────────────────────────────────────────────────────────────
POST_INTERVAL_MINUTES = 60

# ── Authors (alternate one-by-one) ─────────────────────────────────────
AUTHORS = [
    {
        "id": "harsh-sanghani",
        "slug": "harsh-sanghani",
        "name": "Harsh Sanghani"
    },
    {
        "id": "harshil-chovatiya",
        "slug": "harshil-chovatiya",
        "name": "Harshil Chovatiya"
    },
]

# ── Categories pool — the agent picks the best fit for each article ────────
CATEGORIES = [
    {"id": "696ca7a5ecbd8aee584d42a5", "name": "Politics",    "slug": "politics"},
    {"id": "696ca7acecbd8aee584d42a6", "name": "Business",    "slug": "business"},
    {"id": "696ca7bdecbd8aee584d42a8", "name": "World",       "slug": "world"},
    {"id": "696ca804ecbd8aee584d42a9", "name": "Opinion",     "slug": "opinion"},
    {"id": "698dff234880244851228bd1", "name": "Sports",      "slug": "sports"},
    {"id": "696ca7b4ecbd8aee584d42a7", "name": "Technology",  "slug": "technology"},
    {"id": "696ca79eecbd8aee584d42a4", "name": "News",        "slug": "news"},
]

# ── Article types ──────────────────────────────────────────────────────────
ARTICLE_TYPES = ["news", "analysis", "explainer", "updates"]

# ── Search topics to rotate through (US-focused, audience is American) ─────
SEARCH_TOPICS = [
    # ─── US Politics & Government (core) ───
    "US politics Congress White House breaking news today",
    "US presidential administration executive orders news today",
    "US Supreme Court rulings decisions news today",
    "US immigration border policy news today",
    "US election campaign political news today",

    # ─── US Economy & Business ───
    "US economy jobs inflation news today",
    "Wall Street stock market S&P 500 news today",
    "US Federal Reserve interest rate decision news today",
    "US tech companies Silicon Valley news today",
    "US real estate housing market prices news today",

    # ─── US Society & Culture ───
    "US healthcare insurance Medicare Medicaid news today",
    "US education schools college policy news today",
    "US crime public safety news today",
    "US entertainment movies Hollywood celebrity news today",
    "US weather natural disaster news today",

    # ─── US Sports ───
    "NFL football American news today",
    "NBA basketball US news today",
    "MLB baseball US news today",
    "US sports breaking news today",

    # ─── US Military & Defense ───
    "US military Pentagon defense news today",
    "US foreign policy diplomacy news today",

    # ─── US Tech & Science ───
    "US artificial intelligence AI regulation news today",
    "US space NASA SpaceX news today",
    "US cryptocurrency regulation news today",

    # ─── World (US impact angle) ───
    "world news affecting United States today",
    "US China trade relations news today",
    "US NATO Europe alliance news today",
    "Middle East conflict US involvement news today",
]
