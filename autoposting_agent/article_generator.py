"""
Article generator — uses NVIDIA API (LLM) to create substantial,
well-structured news articles from search results.

Improvements:
  • Title: 55-70 chars (meaningful, not truncated)
  • Readability: short paragraphs, varied sentence length, human tone
  • Structure: 5 rotating article templates so every article looks different
  • Featured scoring: LLM rates quality 1-10; score ≥ 8 → is_featured = True
  • Internal links: related topics fetched from DB and woven into content
"""
import json
import logging
import re
import requests

from autoposting_agent.config import (
    NVIDIA_API_KEY,
    NVIDIA_API_URL,
    NVIDIA_MODEL,
    CATEGORIES,
)

logger = logging.getLogger("autoposting_agent.generator")

# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior journalist and editor for TodaysUS, a premium American news publication.
Your audience is American. Write the way skilled human journalists write — not like a corporate press release and definitely not like a generic AI essay.

WRITING RULES:
1. SUBSTANTIAL articles — 700-900 words of real content minimum.
2. SHORT paragraphs — 2-4 sentences each. White space is your friend.
3. VARIED sentence length — mix short punchy lines with richer explanatory ones. Monotone rhythm feels robotic.
4. HUMAN tone — direct, confident, slightly conversational. Use "Here's why that matters." or "The numbers tell a different story." naturally.
5. LEAD sentence — first sentence must grab the reader. State the most important fact first.
6. NO padding phrases like "In today's rapidly evolving landscape" or "In conclusion" or "It is worth noting that".
7. Use proper HTML only: <h2> for section headings, <p> for paragraphs, <strong> for key terms/names, <ul>/<li> for lists, <blockquote> for notable statements.
8. Do NOT include <h1> — the title is rendered separately.
9. Do NOT use markdown — only HTML tags.
10. US perspective always — explain the US angle, economic impact, or policy implications even for world news.
11. American English spelling and conventions.
12. Include at least 4 distinct sections with <h2> subheadings.
13. NEVER fabricate direct quotes attributed to real named people. Use paraphrase or "according to officials".
"""

# ── Article Structure Templates ──────────────────────────────────────────────

STRUCTURE_TEMPLATES = {
    "breaking_news": """
STRUCTURE TO USE — Breaking News:
  <h2>What Happened</h2>       ← core facts, who/what/where/when
  <h2>The Key Details</h2>     ← supporting facts, timeline, numbers
  <h2>Reactions & Response</h2>← official statements, political/public reaction
  <h2>What's at Stake</h2>     ← implications, risks, what happens next
  <h2>Background</h2>          ← needed context for readers unfamiliar with the issue
""",
    "analysis": """
STRUCTURE TO USE — Deep Analysis:
  <h2>The Big Picture</h2>     ← frame the issue with the key tension or question
  <h2>How We Got Here</h2>     ← historical/policy context
  <h2>The Numbers</h2>         ← data, statistics, economic figures
  <h2>Competing Perspectives</h2>← two or more viewpoints (no personal opinion)
  <h2>What Experts Say</h2>    ← paraphrased expert analysis
  <h2>Looking Ahead</h2>       ← scenarios, timelines, what to watch
""",
    "explainer": """
STRUCTURE TO USE — Explainer:
  <h2>The Short Answer</h2>    ← 1-2 sentence summary of the core issue
  <h2>Why It's Happening Now</h2> ← triggers, recent events that made this news
  <h2>Who's Involved</h2>      ← key players: politicians, agencies, companies, groups
  <h2>What It Means for Americans</h2> ← direct impact: jobs, prices, rights, safety
  <h2>The Bigger Debate</h2>   ← political/social context, ongoing controversy
  <h2>Key Terms Explained</h2> ← brief glossary of 3-4 relevant terms (use <ul>)
""",
    "policy_update": """
STRUCTURE TO USE — Policy Update:
  <h2>The Change</h2>          ← exactly what policy/law/rule changed and when
  <h2>Who It Affects</h2>      ← specific groups: workers, consumers, businesses, states
  <h2>The Debate in Washington</h2> ← congressional/White House debate
  <h2>State-Level Response</h2>← how governors / state AGs are reacting
  <h2>Timeline</h2>            ← when it takes effect, key upcoming dates (use <ul>)
  <h2>What Happens Next</h2>   ← legal challenges, congressional action, elections
""",
    "impact_story": """
STRUCTURE TO USE — Human Impact Story:
  <h2>The Situation</h2>       ← scene-setting: what's happening on the ground
  <h2>By the Numbers</h2>      ← statistics that put the scale in context
  <h2>Voices from the Ground</h2> ← paraphrased perspectives of affected Americans
  <h2>The Policy Behind It</h2>← what government decisions led here
  <h2>Is Relief in Sight?</h2> ← proposed solutions, congressional action, timeline
  <h2>The Broader Lesson</h2>  ← wider takeaway for American society/policy
""",
}

# ── Generation Prompt ────────────────────────────────────────────────────────

GENERATION_PROMPT = """Based on this trending US news topic, write a complete, high-quality news article.

**Topic:** {title}
**Context:** {snippet}
**Search Category:** {search_topic}
**Article Structure to follow:** {structure_name}

{structure_instructions}

TITLE RULES:
- Between 55 and 70 characters (count carefully).
- Must be a complete, meaningful sentence or tight headline — never cut off mid-thought.
- Compelling, SEO-friendly, and specific. Avoid vague titles like "News Update" or "Important Changes".
- Example of BAD title (too short): "Trump Signs Bill" (15 chars — too vague)
- Example of GOOD title: "Trump Signs Sweeping Border Bill, Reshaping Immigration Law" (58 chars)

FEATURED SCORING:
Rate your own article on a 1-10 scale based on:
- Depth of analysis and research quality
- Newsworthiness and timeliness
- Writing quality and originality
- If score is 8 or higher, set "is_featured": true

You MUST respond with valid JSON only (no markdown fences, no extra text):
{{
    "title": "Complete headline between 55-70 characters",
    "excerpt": "2-3 sentence hook that encourages reading (150-200 chars)",
    "content_html": "<h2>...</h2><p>...</p>... (full article, 700-900+ words, multiple sections per structure above)",
    "seo_title": "SEO title 50-60 chars",
    "seo_description": "Meta description 150-160 chars",
    "category_slug": "one of: politics, business, world, opinion, sports, technology, news",
    "topics": ["topic1", "topic2", "topic3", "topic4", "topic5"],
    "type": "{article_type}",
    "quality_score": 7,
    "is_featured": false
}}

Remember: SHORT paragraphs. HUMAN voice. NO AI padding phrases. COMPLETE title only."""


def _pick_structure(search_result: dict) -> tuple[str, str]:
    """
    Choose the best article structure based on the search topic keyword hints.
    Returns (structure_name, structure_instructions).
    """
    topic_lower = (search_result.get("search_topic", "") + " " + search_result.get("title", "")).lower()

    if any(k in topic_lower for k in ["policy", "law", "bill", "executive order", "regulation", "medicare", "immigration border"]):
        name = "policy_update"
    elif any(k in topic_lower for k in ["breaking", "shooting", "crash", "explosion", "emergency", "hurricane", "disaster"]):
        name = "breaking_news"
    elif any(k in topic_lower for k in ["explain", "what is", "how", "why", "understand", "education", "cryptocurrency"]):
        name = "explainer"
    elif any(k in topic_lower for k in ["economy", "jobs", "inflation", "housing", "wages", "poverty", "healthcare insurance", "crime"]):
        name = "impact_story"
    else:
        name = "analysis"

    return name, STRUCTURE_TEMPLATES[name]


def _map_type_from_structure(structure_name: str) -> str:
    mapping = {
        "breaking_news": "news",
        "analysis": "analysis",
        "explainer": "explainer",
        "policy_update": "updates",
        "impact_story": "news",
    }
    return mapping.get(structure_name, "news")


def generate_article(search_result: dict, internal_links: list[dict] | None = None) -> dict | None:
    """
    Call NVIDIA API to generate a full article from a search result.
    internal_links: list of {"name": str, "slug": str, "url": str} for weaving into content.
    Returns a parsed article dict or None on failure.
    """
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY is not set!")
        return None

    structure_name, structure_instructions = _pick_structure(search_result)
    article_type = _map_type_from_structure(structure_name)

    # Build internal link context for the LLM
    internal_link_hint = ""
    if internal_links:
        links_list = "\n".join(
            f'  - "{lnk["name"]}" → <a href="{lnk["url"]}">{lnk["name"]}</a>'
            for lnk in internal_links[:6]
        )
        internal_link_hint = f"""
INTERNAL LINKS (weave naturally into content — do not list them separately):
{links_list}
Use these as contextual hyperlinks within sentences where they fit naturally. Do NOT force all of them in."""

    prompt = GENERATION_PROMPT.format(
        title=search_result["title"],
        snippet=search_result["snippet"],
        search_topic=search_result["search_topic"],
        structure_name=structure_name.replace("_", " ").title(),
        structure_instructions=structure_instructions,
        article_type=article_type,
    )

    if internal_link_hint:
        prompt += "\n" + internal_link_hint

    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.72,
        "top_p": 0.92,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        logger.info(f"🤖 Generating article via NVIDIA API (structure: {structure_name})...")
        resp = requests.post(
            NVIDIA_API_URL,
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # ── Robust JSON extraction ─────────────────────────────────────────
        # Strip markdown fences
        content = re.sub(r'^```(?:json)?\s*\n?', '', content)
        content = re.sub(r'\n?```\s*$', '', content)
        content = content.strip()

        # Extract JSON object if extra text exists
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()

        # Fix raw newlines / tabs inside JSON strings
        def fix_control_chars(s: str) -> str:
            result = []
            in_string = False
            i = 0
            while i < len(s):
                ch = s[i]
                if ch == '"' and (i == 0 or s[i - 1] != '\\'):
                    in_string = not in_string
                    result.append(ch)
                elif in_string and ch in '\n\r\t':
                    if ch == '\n':
                        result.append('\\n')
                    elif ch == '\r':
                        result.append('\\r')
                    elif ch == '\t':
                        result.append('\\t')
                else:
                    result.append(ch)
                i += 1
            return ''.join(result)

        content = fix_control_chars(content)

        try:
            article_data = json.loads(content)
        except json.JSONDecodeError:
            article_data = json.loads(content, strict=False)

        # ── Validate required fields ───────────────────────────────────────
        required = ["title", "excerpt", "content_html", "category_slug", "topics"]
        for field in required:
            if field not in article_data:
                logger.error(f"Missing field in generated article: {field}")
                return None

        # ── Title length guard — pad if too short, trim if too long ───────
        title = article_data["title"].strip()
        if len(title) < 40:
            logger.warning(f"⚠️  Title too short ({len(title)} chars): '{title}' — flagging for regeneration attempt")
            # Append category context to nudge a longer title
            title = f"{title} — What Americans Need to Know"
            article_data["title"] = title
        elif len(title) > 80:
            # Hard-trim at word boundary
            title = title[:77].rsplit(" ", 1)[0] + "..."
            article_data["title"] = title
        logger.info(f"   Title ({len(article_data['title'])} chars): {article_data['title']}")

        # ── Resolve category ───────────────────────────────────────────────
        cat_slug = article_data.get("category_slug", "world")
        category = next(
            (c for c in CATEGORIES if c["slug"] == cat_slug),
            CATEGORIES[2],
        )
        article_data["category"] = category

        # ── Convert topic strings to topic objects ─────────────────────────
        article_data["topics"] = [
            {"name": t, "slug": t.lower().replace(" ", "-")}
            for t in article_data.get("topics", [])[:5]
        ]

        # ── Featured flag ──────────────────────────────────────────────────
        quality_score = int(article_data.get("quality_score", 0))
        is_featured = bool(article_data.get("is_featured", False)) or quality_score >= 8
        article_data["is_featured"] = is_featured
        article_data["quality_score"] = quality_score

        # ── Store structure info ───────────────────────────────────────────
        article_data["article_structure"] = structure_name

        logger.info(
            f"✅ Generated: [{structure_name}] Q:{quality_score}/10 "
            f"{'⭐ FEATURED' if is_featured else ''} | {article_data['title']}"
        )
        return article_data

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        logger.error(f"Raw content (first 800 chars): {content[:800]}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"NVIDIA API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in generate_article: {e}", exc_info=True)
        return None
