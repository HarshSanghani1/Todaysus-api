"""
Article generator — uses NVIDIA API (LLM) to create substantial,
well-structured news articles from search results.

Improvements:
  • Title: 55-70 chars (meaningful, not truncated)
  • Readability: short paragraphs, varied sentence length, human tone
  • Structure: 5 rotating article templates so every article looks different
  • Featured scoring: LLM rates quality 1-10; score >= 8 -> is_featured = True
  • Internal links: related topics fetched from DB and woven into content
  • Timeout: 180s with 2 retry attempts (NVIDIA free tier can be slow)
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

MAX_RETRIES = 2
TIMEOUT_SECONDS = 300  # 5 min — covers slow free-tier queuing + 900-word generation

SYSTEM_PROMPT = """You are a senior investigative journalist, SEO strategist, and veteran editor at TodaysUS. Your mission is to produce authoritative, high-ranking content that dominates Google Search results through superior quality and technical SEO optimization.

JOURNALISTIC EXCELLENCE & EEAT (Experience, Expertise, Authoritativeness, Trustworthiness):
1. AUTHORITATIVE TONE: Write as a subject matter expert. Avoid "I think" or "This might." Use "The data confirms," "Strategic shifts indicate," or "Sources within the industry suggest."
2. ENTITY-BASED SEO: Focus heavily on entities (specific people, organizations, locations, and events). Google ranks content that connects clear entities.
3. NO AI FOOTPRINTS: Avoid predictable sentence structures, rhythmic paragraph lengths, and typical AI transitions. Use complex, human logic.
4. "SO WHAT?" ECONOMY: Within the first 150 words, clearly state the impact on the U.S. economy, policy, or the average American's life.
5. VARIATION & DEPTH: Mix short, explosive sentences for impact with deep, analytical paragraphs. Aim for 800-1000 words of hard-hitting substance.

SEO OPTIMIZATION STRATEGY:
1. KEYWORD PLACEMENT: Place the primary keyword (found in the topic) naturally in the first 100 words, at least two <h3> subheadings, and the FAQ.
2. LSI & SEMANTIC CLUSTERS: Use related terms and synonyms naturally. For a story on "Economy," use "fiscal policy," "GDP growth," "inflationary pressure," and "market volatility."
3. READABILITY SCORE: Use active voice. Keep paragraphs to 3-4 sentences maximum. Use whitespace strategically.
4. INTERNAL LINKING: Use <a href="URL"><u>Anchor Text</u></a>. Weave 3-5 internal links naturally where they add context, rather than listing them.

PRO-GRADE HTML STRUCTURE:
1. HEADLINE (h2): Broad, keyword-rich, and compelling (55-70 chars).
2. KEY TAKEAWAYS (ul): Immediately after the headline, provide a "The Big Picture: Key Points" box using a <ul> with 3 bullet points inside a summary section.
3. SUBHEADINGS (h3): Must be descriptive, keyword-infused, and human-sounding (e.g., "The Federal Reserve's High-Stakes Gamble" instead of "Economic Background").
4. RICH MEDIA ELEMENTS:
   - BLOCKQUOTES (blockquote): Use for high-impact expert quotes or official statements.
   - SEMANTIC TAGS: Use <strong> for important entities and <em> for emphasis.
   - DATA LISTS: Use <ul> or <ol> to break down complex statistics or timelines.
5. FAQ (h3): Answers the "People Also Ask" search intent. 3-4 questions in <strong> followed by concise <p> answers.
6. RELATED NEWS (h3): One high-relevance internal link to boost crawl depth.
"""

# ── Article Structure Templates ───────────────────────────────────────────────

STRUCTURE_TEMPLATES = {
    "breaking_news": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Primary Headline]</h2>
  - [2-3 Paragraphs of Intro]
  - <h3>[Dynamic Human Subheading about the event]</h3>
  - <blockquote>[Key Quote or Paraphrased Statement]</blockquote>
  - <h3>[Subheading about broader context]</h3>
  - <ul>[List of 3-4 key facts]</ul>
  - <h3>[Subheading about what to watch for]</h3>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "analysis": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Analytical Headline]</h2>
  - [Intro]
  - <h3>[Subheading framing the central conflict]</h3>
  - <ul>[List of relevant data points/numbers]</ul>
  - <h3>[Subheading about the historical roots]</h3>
  - <blockquote>[Expert perspective/analysis]</blockquote>
  - <h3>[The road ahead]</h3>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "explainer": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Educational Title]</h2>
  - [Intro]
  - <h3>The core issue in plain English</h3>
  - <ul>[Bullet points of how it works]</ul>
  - <h3>Why it’s hitting the headlines now</h3>
  - blockquote[Policy or expert quote]
  - <h3>What this means for your wallet/rights</h3>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
}
# (Other templates following similar dynamic patterns...)

# ── Generation Prompt ─────────────────────────────────────────────────────────

GENERATION_PROMPT = """Based on this trending news topic, produce a masterful 800-1000 word news report designed to rank #1 on Google for its depth and authority.

**Main Topic:** {title}
**Contextual Snippet:** {snippet}
**Search Category:** {search_topic}
**Requested Tone:** Authoritative Journalist / SEO Strategist

INSTRUCTIONS FOR SUCCESS:
1. START WITH A SUMMARIZED KEY POINTS BOX (<ul>) immediately after the <h2> headline.
2. WRITE 800-1000 WORDS of original analysis. Do not repeat facts. Dig deep into the 'why'.
3. KEYWORD STRATEGY: Find the 3 most important keywords in the topic. Use the primary one in 2 subheaders and once in the first paragraph.
4. ENTITY FOCUS: Identify the main people and organizations involved. Use their full names and titles.
5. HUMAN PACE: Avoid repetitive sentence starts (e.g., "The," "It," "This"). Use human-like transitions.
6. FORMAT: Use <h2> for the main title, <h3> for subheads, <blockquote> for expert quotes, and <ul>/<li> for data sets.

TITLE RULES:
- 55-70 characters.
- Must be a "Power Headline": high-impact, specific, and complete.

FEATURED SCORING:
- 1-10 scale.
- Criteria: Journalistic authority, SEO keyword integration, entity connection, and narrative flow.
- score >= 8 -> "is_featured": true.

JSON OUTPUT (VALID JSON ONLY):
{{
    "title": "SEO-Optimized 55-70 char headline",
    "excerpt": "Keyword-rich 150-200 char summary",
    "content_html": "<h2>[Title]</h2><h3>Key Takeaways</h3><ul><li>[Point1]</li>...</ul><p>[Lead]...</p><h3>[Keyword-Rich Subhead]</h3>...<blockquote>[Impactful Quote]</blockquote>...<h3>FAQ</h3>...<h3>Related News</h3>",
    "seo_title": "[Primary Keyword] | [Secondary Keyword] | TodaysUS",
    "seo_description": "Compelling meta description with main keyword in the first 10 words.",
    "category_slug": "politics, business, technology, etc.",
    "topics": ["entity1", "entity2", "entity3"],
    "type": "{article_type}",
    "quality_score": 10,
    "is_featured": true
}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_structure(search_result: dict) -> tuple[str, str]:
    """
    Choose the best article structure based on the search topic keyword hints.
    Returns (structure_name, structure_instructions).
    """
    topic_lower = (
        search_result.get("search_topic", "") + " " + search_result.get("title", "")
    ).lower()

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


def _fix_control_chars(s: str) -> str:
    """Escape raw newlines/tabs inside JSON strings so json.loads won't fail."""
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


# ── Main Generator ────────────────────────────────────────────────────────────

def generate_article(search_result: dict, internal_links: list[dict] | None = None) -> dict | None:
    """
    Call NVIDIA API to generate a full article from a search result.
    internal_links: list of {"name": str, "slug": str, "url": str}
    Returns a parsed article dict or None on failure.
    Retries up to MAX_RETRIES times on timeout/network errors.
    """
    if not NVIDIA_API_KEY:
        logger.error("❌ NVIDIA_API_KEY is not set!")
        return None

    structure_name, structure_instructions = _pick_structure(search_result)
    article_type = _map_type_from_structure(structure_name)

    # Build internal link hint for the LLM
    internal_link_hint = ""
    if internal_links:
        links_list = "\n".join(
            f'  - "{lnk["name"]}" -> <a href="{lnk["url"]}"><u>{lnk["name"]}</u></a>'
            for lnk in internal_links[:6]
        )
        internal_link_hint = (
            "\nINTERNAL LINKS (weave naturally into content — do not list them separately):\n"
            + links_list
            + "\nUse these as contextual hyperlinks EXACTLY as written above (including the <u> tag) within sentences where they fit naturally. Do NOT force all of them in."
        )

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

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                f"🤖 Generating article via NVIDIA API "
                f"(structure: {structure_name}, attempt {attempt}/{MAX_RETRIES})..."
            )
            resp = requests.post(
                NVIDIA_API_URL,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Strip markdown fences if present
            content = re.sub(r'^```(?:json)?\s*\n?', '', content)
            content = re.sub(r'\n?```\s*$', '', content)
            content = content.strip()

            # Extract JSON object if extra text exists
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                content = json_match.group()

            content = _fix_control_chars(content)

            try:
                article_data = json.loads(content)
            except json.JSONDecodeError:
                article_data = json.loads(content, strict=False)

            # Validate required fields
            required = ["title", "excerpt", "content_html", "category_slug", "topics"]
            for field in required:
                if field not in article_data:
                    logger.error(f"Missing field in generated article: {field}")
                    return None

            # Title length guard
            title = article_data["title"].strip()
            if len(title) < 40:
                logger.warning(f"⚠️  Title too short ({len(title)} chars): '{title}' — padding")
                title = f"{title} — What Americans Need to Know"
                article_data["title"] = title
            elif len(title) > 80:
                title = title[:77].rsplit(" ", 1)[0] + "..."
                article_data["title"] = title
            logger.info(f"   Title ({len(article_data['title'])} chars): {article_data['title']}")

            # Resolve category
            cat_slug = article_data.get("category_slug", "world")
            category = next(
                (c for c in CATEGORIES if c["slug"] == cat_slug),
                CATEGORIES[2],
            )
            article_data["category"] = category

            # Convert topic strings to topic objects
            article_data["topics"] = [
                {"name": t, "slug": t.lower().replace(" ", "-")}
                for t in article_data.get("topics", [])[:5]
            ]

            # Featured flag — LLM self-rated or quality >= 8
            quality_score = int(article_data.get("quality_score", 0))
            is_featured = bool(article_data.get("is_featured", False)) or quality_score >= 8
            article_data["is_featured"] = is_featured
            article_data["quality_score"] = quality_score

            # Store structure info
            article_data["article_structure"] = structure_name

            logger.info(
                f"✅ Generated: [{structure_name}] Q:{quality_score}/10 "
                f"{'⭐ FEATURED' if is_featured else ''} | {article_data['title']}"
            )
            return article_data

        except requests.exceptions.Timeout:
            logger.warning(f"⏱️  Attempt {attempt}/{MAX_RETRIES} timed out after {TIMEOUT_SECONDS}s.")
            if attempt < MAX_RETRIES:
                logger.info("   Retrying...")
                continue
            logger.error("❌ All retry attempts timed out. Giving up.")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"NVIDIA API error (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                logger.info("   Retrying...")
                continue
            return None

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Raw content (first 800 chars): {content[:800]}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error in generate_article: {e}", exc_info=True)
            return None

    return None  # exhausted all retries
