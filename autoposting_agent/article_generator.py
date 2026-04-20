"""
Article generator — uses NVIDIA API (LLM) to create substantial,
well-structured news articles from search results.
"""
import json
import logging
import requests

from autoposting_agent.config import (
    NVIDIA_API_KEY,
    NVIDIA_API_URL,
    NVIDIA_MODEL,
    CATEGORIES,
)

logger = logging.getLogger("autoposting_agent.generator")

SYSTEM_PROMPT = """You are a senior journalist and editor for TodaysUS, a premium US news publication.
Your audience is American. Your job is to write comprehensive, well-researched, and engaging news articles.

RULES:
1. Write SUBSTANTIAL articles — minimum 600-800 words of actual content.
2. Use proper HTML formatting: <h2> for section headings, <p> for paragraphs, <strong> for emphasis, <ul>/<li> for lists where appropriate.
3. Include multiple sections with clear subheadings.
4. Write in a professional, authoritative journalistic tone.
5. Include context, background, expert perspectives, and future implications.
6. Do NOT use markdown — only HTML tags.
7. Do NOT include <h1> (the title is separate).
8. Make the content informative, detailed, and newsworthy.
9. Generate realistic but clearly editorial content — do not fabricate specific quotes with attribution to real people.
10. Include analysis sections like "What This Means", "Background", "Expert Analysis", "Looking Ahead".
11. ALWAYS write from a US perspective. Even for world news, explain how it impacts Americans, the US economy, or US foreign policy.
12. Use American English spelling and conventions.
"""

GENERATION_PROMPT = """Based on this trending news topic, write a complete, substantial news article:

**Topic:** {title}
**Context:** {snippet}
**Search Category:** {search_topic}

You MUST respond with valid JSON only (no markdown fences, no extra text). Use this exact format:
{{
    "title": "A compelling, SEO-friendly headline (50-80 chars)",
    "excerpt": "A 2-3 sentence summary that hooks the reader (150-200 chars)",
    "content_html": "<h2>...</h2><p>...</p>... (full article with 600-800+ words, multiple sections)",
    "seo_title": "SEO optimized title (50-60 chars)",
    "seo_description": "Meta description for search engines (150-160 chars)",
    "category_slug": "best matching slug from: politics, business, world, opinion, sports, technology, news",
    "topics": ["topic1", "topic2", "topic3", "topic4"],
    "type": "news or analysis or explainer or updates"
}}

Write a LONG, DETAILED article. Short articles are unacceptable. Include at least 4-5 sections with subheadings."""


def generate_article(search_result: dict) -> dict | None:
    """
    Call NVIDIA API to generate a full article from a search result.
    Returns a parsed article dict or None on failure.
    """
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY is not set!")
        return None

    prompt = GENERATION_PROMPT.format(
        title=search_result["title"],
        snippet=search_result["snippet"],
        search_topic=search_result["search_topic"],
    )

    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        logger.info("🤖 Generating article via NVIDIA API...")
        resp = requests.post(
            NVIDIA_API_URL,
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # ── Robust JSON extraction ──────────────────────────────────────
        import re

        # Strip markdown fences
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        content = re.sub(r'\n?```\s*$', '', content)
        content = content.strip()

        # Try to extract JSON object if there's extra text around it
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()

        # Fix control characters inside JSON strings (LLMs put real newlines in strings)
        # We need to be careful: preserve \n that are already escaped
        def fix_control_chars(s):
            result = []
            i = 0
            in_string = False
            while i < len(s):
                ch = s[i]
                if ch == '"' and (i == 0 or s[i-1] != '\\'):
                    in_string = not in_string
                    result.append(ch)
                elif in_string and ch in '\n\r\t':
                    result.append({'\\n': '\\\\n', '\\r': '\\\\r', '\\t': '\\\\t'}[repr(ch)[1:-1].replace("'", "")])
                    # Simpler: just replace with escaped version
                    if ch == '\n': result[-1] = '\\n'
                    elif ch == '\r': result[-1] = '\\r'
                    elif ch == '\t': result[-1] = '\\t'
                else:
                    result.append(ch)
                i += 1
            return ''.join(result)

        content = fix_control_chars(content)

        try:
            article_data = json.loads(content)
        except json.JSONDecodeError:
            # Last resort: try with strict=False
            article_data = json.loads(content, strict=False)

        # Validate required fields
        required = ["title", "excerpt", "content_html", "category_slug", "topics"]
        for field in required:
            if field not in article_data:
                logger.error(f"Missing field in generated article: {field}")
                return None

        # Resolve category
        cat_slug = article_data.get("category_slug", "world")
        category = next(
            (c for c in CATEGORIES if c["slug"] == cat_slug),
            CATEGORIES[2],  # fallback to "World"
        )
        article_data["category"] = category

        # Convert topic strings to topic objects
        article_data["topics"] = [
            {"name": t, "slug": t.lower().replace(" ", "-")}
            for t in article_data.get("topics", [])[:5]
        ]

        logger.info(f"✅ Generated: {article_data['title']}")
        return article_data

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        logger.error(f"Raw content (first 800 chars): {content[:800]}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"NVIDIA API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None
