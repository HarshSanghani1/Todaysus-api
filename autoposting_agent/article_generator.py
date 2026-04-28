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
    CATEGORIES,
    NVIDIA_API_KEY,
    NVIDIA_API_URL,
    NVIDIA_MODEL,
)

logger = logging.getLogger("autoposting_agent.generator")

MAX_RETRIES = 2
TIMEOUT_SECONDS = 300  # 5 min — covers slow free-tier queuing + 900-word generation

SYSTEM_PROMPT = """You are a senior journalist and editor at TodaysUS. Your ONLY job is to rewrite the provided source article into a high-quality, SEO-optimized news piece — staying 100% faithful to the source material.

CRITICAL GROUNDING RULES (violating these is a failure):
1. STAY ON TOPIC: Only write about what is explicitly described in the SOURCE TEXT below. Do not introduce new subjects, technologies, companies, or concepts that are not in the source.
2. NO INVENTION: Never add facts, quotes, statistics, or opinions that are not directly supported by the source text. If the source doesn't mention AI, do not mention AI.
3. NO TOPIC DRIFT: The article must cover ONE story — the story from the source. Do not try to cover "related" or "broader" themes unless they are directly discussed in the source.
4. ONE SUBJECT: If the source is about GM delaying electric trucks, the article is ONLY about that. Do not pivot to battery technology trends, AI in EVs, or competitor strategies unless the source explicitly covers those.

JOURNALISTIC STANDARDS:
1. AUTHORITATIVE TONE: Write as a subject-matter expert. Use declarative, confident language.
2. ENTITY FOCUS: Use full names of real people, organizations, and locations mentioned in the source.
3. HUMAN WRITING: Vary sentence length. Mix short punchy sentences with deeper analytical ones. No AI-sounding cadence.
4. IMPACT FIRST: In the first 150 words, state why this story matters to Americans.

SEO RULES:
1. KEYWORD PLACEMENT: Use the primary keyword from the headline naturally in the first paragraph and in at least two <h3> subheadings.
2. READABILITY: Active voice. Short paragraphs (3-4 sentences max). Strategic whitespace.
3. INTERNAL LINKING: Use <a href="URL"><u>Anchor Text</u></a> for provided internal links — only insert them where they fit the article's actual subject matter.

PRO-GRADE HTML STRUCTURE:
1. HEADLINE (h2): 55-70 characters. Specific to THIS story.
2. KEY TAKEAWAYS (ul): 3 bullet points summarizing the source article's main facts, right after the <h2>.
3. SUBHEADINGS (h3): Descriptive, keyword-rich, human-sounding. Reflect the source's actual content.
4. BLOCKQUOTES: Use for real quotes or paraphrased statements from people/organizations in the source.
5. FAQ (h3): 3-4 questions that readers would ask about THIS specific story.
6. RELATED NEWS (h3): One internal link relevant to this story's actual topic.
"""

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

GENERATION_PROMPT = """Rewrite the source article below into a polished, SEO-optimized 700-900 word news piece for TodaysUS. Your article must be grounded EXCLUSIVELY in the source text — do not add topics, technologies, or themes that are not present in the source.

**Headline / Story:** {title}
**Category:** {search_topic}

--- SOURCE ARTICLE (base your entire article on THIS content only) ---
{source_text}
--- END SOURCE ARTICLE ---

STRICT INSTRUCTIONS:
1. SINGLE TOPIC ONLY: This article covers exactly one story. Do not pivot to adjacent topics not in the source.
2. KEY POINTS BOX: Start with a <h3>The Big Picture: Key Points</h3> followed by a <ul> of exactly 3 bullet points that summarize the source's main facts.
3. 700-900 WORDS: Rewrite the source into a complete, well-structured piece. Expand on what the source says — do NOT invent new facts.
4. ENTITY ACCURACY: Use the exact names of people, companies, and places as they appear in the source.
5. HUMAN TONE: Active voice. Varied sentence rhythm. Confident, non-repetitive.
6. HTML FORMAT: Use <h2> for the main title, <h3> for subheadings, <blockquote> for quotes that exist in the source, <ul>/<li> for lists of facts from the source.
7. FAQ: 3 questions a reader would ask about THIS specific story, answered from source facts only.
8. RELATED NEWS: One internal link from the provided internal links list, only if it genuinely relates to this story's topic.
9. WORD COUNT IS MANDATORY: You must produce at least 700 words. Do not use placeholders. Write the full analysis.

TITLE RULES:
- 55-70 characters. Specific and accurate to the source story.

FEATURED SCORING:
- 1-10. Based on: source accuracy, journalistic quality, SEO, entity precision.
- score >= 8 -> "is_featured": true.

JSON OUTPUT (VALID JSON ONLY; DO NOT OUTPUT RAW HTML OUTSIDE THIS OBJECT):
{{
    "title": "SEO-optimized headline matching the source story",
    "excerpt": "Accurate 150-200 char summary",
    "content_html": "<h2... Write the full 700-900 word article here. Do NOT use the word 'placeholder' or '...'. Write every paragraph in full detail.>",
    "seo_title": "[Primary Keyword] | TodaysUS",
    "seo_description": "Meta description...",
    "category_slug": "news",
    "topics": ["topic1", "topic2"],
    "type": "{article_type}",
    "quality_score": 8,
    "is_featured": true
}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_structure(search_result: dict) -> tuple[str, str]:
    topic_lower = (
        search_result.get("search_topic", "") + " " + search_result.get("title", "")
    ).lower()

    if any(
        k in topic_lower
        for k in [
            "policy",
            "law",
            "bill",
            "executive order",
            "regulation",
            "medicare",
            "immigration border",
        ]
    ):
        name = "policy_update"
    elif any(
        k in topic_lower
        for k in ["breaking", "shooting", "crash", "explosion", "emergency", "hurricane", "disaster"]
    ):
        name = "breaking_news"
    elif any(
        k in topic_lower
        for k in ["explain", "what is", "how", "why", "understand", "education", "cryptocurrency"]
    ):
        name = "explainer"
    elif any(
        k in topic_lower
        for k in ["economy", "jobs", "inflation", "housing", "wages", "poverty", "healthcare insurance", "crime"]
    ):
        name = "impact_story"
    else:
        name = "analysis"

    return name, STRUCTURE_TEMPLATES.get(name, STRUCTURE_TEMPLATES["analysis"])


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

    # Use source_text if available; fall back to snippet so the LLM is always grounded
    source_text = search_result.get("source_text", "").strip()
    if not source_text:
        source_text = search_result.get("snippet", "")
    # Truncate to avoid token overflows while keeping enough grounding material
    if len(source_text) > 8000:
        source_text = source_text[:8000].rsplit(" ", 1)[0] + "..."

    prompt = GENERATION_PROMPT.format(
        title=search_result["title"],
        snippet=search_result.get("snippet", ""),
        search_topic=search_result["search_topic"],
        source_text=source_text,
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
