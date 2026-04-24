"""
Article generator - uses NVIDIA API (LLM) to create substantial,
well-structured news articles from search results.

Generation pipeline:
  1. Draft a full article.
  2. Expand if the draft is below the publishable word minimum.
  3. Polish if SEO/article-structure requirements are missing.
"""
import html
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
TIMEOUT_SECONDS = 300
MIN_PUBLISH_WORDS = 700
TARGET_WORDS = "800-1000"
EXPANSION_TARGET_WORDS = 900
LLM_JSON_MAX_TOKENS = 6144

SYSTEM_PROMPT = """You are a senior investigative journalist, SEO strategist, and veteran editor at TodaysUS. Your mission is to produce authoritative, high-ranking content that dominates Google Search results through superior quality and technical SEO optimization.

JOURNALISTIC EXCELLENCE & EEAT (Experience, Expertise, Authoritativeness, Trustworthiness):
1. AUTHORITATIVE TONE: Write as a subject matter expert. Avoid "I think" or "This might." Use "The data confirms," "Strategic shifts indicate," or "industry analysts are watching."
2. ENTITY-BASED SEO: Focus heavily on entities: specific people, organizations, locations, agencies, companies, laws, and events.
3. NO AI FOOTPRINTS: Avoid predictable sentence structures, rhythmic paragraph lengths, filler transitions, and generic summaries.
4. "SO WHAT?" ECONOMY: Within the first 150 words, clearly state the impact on U.S. policy, business, markets, public safety, technology, or daily life.
5. DEPTH REQUIREMENT: Produce 800-1000 words of hard-hitting substance. If the article is under 700 words, you have failed. Use investigative detail, stakeholder analysis, historical context, policy/business impact, and what-to-watch reporting to reach the required length.

SEO OPTIMIZATION STRATEGY:
1. KEYWORD PLACEMENT: Place the primary keyword naturally in the first 100 words, at least two <h3> subheadings, and the FAQ.
2. LSI & SEMANTIC CLUSTERS: Use related terms and synonyms naturally. For a story on "Economy," use terms like "fiscal policy," "GDP growth," "inflationary pressure," and "market volatility" where relevant.
3. READABILITY SCORE: Use active voice. Keep paragraphs to 3-4 sentences maximum. Use whitespace strategically.
4. INTERNAL LINKING: Use <a href="URL"><u>Anchor Text</u></a>. Weave 3-5 internal links naturally where they add context.

PRO-GRADE HTML STRUCTURE:
1. HEADLINE (h2): Broad, keyword-rich, and compelling (55-70 chars).
2. KEY TAKEAWAYS (ul): Immediately after the headline, provide "The Big Picture: Key Points" using a <h3> and a <ul> with 3 bullet points.
3. SUBHEADINGS (h3): Include 6-8 descriptive, keyword-infused subsections. Each main subsection should include at least 3 substantive paragraphs unless it is a FAQ or Related News section.
4. RICH MEDIA ELEMENTS: Include at least two <blockquote> sections for official statements, clearly attributed reporting context, or quote-style expert analysis. Do not invent direct quotes.
5. SEMANTIC TAGS: Use <strong> for important entities and <em> for emphasis throughout the article body.
6. DATA LISTS: Use <ul> or <ol> to break down complex statistics, timelines, or stakeholder impacts.
7. FAQ (h3): Include 5+ long-tail questions in <strong> tags followed by concise <p> answers.
8. RELATED NEWS (h3): Include one high-relevance internal link to boost crawl depth.
"""

STRUCTURE_TEMPLATES = {
    "breaking_news": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Primary Headline]</h2>
  - <h3>The Big Picture: Key Points</h3><ul>[3 fresh key points]</ul>
  - [2-3 Paragraphs of immediate news impact]
  - <h3>[What happened and why it matters]</h3>
  - <h3>[The people, agencies, or companies at the center]</h3>
  - <blockquote>[Official statement or clearly framed expert analysis]</blockquote>
  - <h3>[The broader U.S. impact]</h3>
  - <ul>[3-4 key facts, numbers, or timeline points]</ul>
  - <h3>[What changes next]</h3>
  - <blockquote>[Second official/expert-analysis blockquote]</blockquote>
  - <h3>[What Americans should watch]</h3>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "analysis": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Analytical Headline]</h2>
  - <h3>The Big Picture: Key Points</h3><ul>[3 strategic points]</ul>
  - [2-3 Paragraphs of analytical lead]
  - <h3>[The central conflict behind the news]</h3>
  - <h3>[Key entities and incentives]</h3>
  - <ul>[Relevant data points, dates, and numbers]</ul>
  - <h3>[Historical roots and policy/business context]</h3>
  - <blockquote>[Clearly attributed analysis or official framing]</blockquote>
  - <h3>[Market, political, or consumer impact]</h3>
  - <h3>[The road ahead]</h3>
  - <blockquote>[Second expert-analysis blockquote]</blockquote>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "explainer": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Educational Title]</h2>
  - <h3>The Big Picture: Key Points</h3><ul>[3 plain-English points]</ul>
  - [2-3 Paragraphs of plain-English lead]
  - <h3>The core issue in plain English</h3>
  - <ul>[How it works]</ul>
  - <h3>Why it is hitting headlines now</h3>
  - <blockquote>[Policy, company, or expert-analysis framing]</blockquote>
  - <h3>The timeline that led here</h3>
  - <h3>What it means for households, workers, or investors</h3>
  - <h3>What happens next</h3>
  - <blockquote>[Second expert-analysis blockquote]</blockquote>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "policy_update": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Policy-Focused Headline]</h2>
  - <h3>The Big Picture: Key Points</h3><ul>[3 policy stakes]</ul>
  - [2-3 Paragraphs explaining the new action]
  - <h3>[What the White House, Congress, court, or agency changed]</h3>
  - <h3>[Who gains, who loses, and who is pushing back]</h3>
  - <blockquote>[Official statement or clearly labeled policy analysis]</blockquote>
  - <h3>[Legal, budget, or enforcement context]</h3>
  - <ul>[Timeline, deadlines, or affected groups]</ul>
  - <h3>[How this affects Americans]</h3>
  - <h3>[What happens next in Washington]</h3>
  - <blockquote>[Second official/expert-analysis blockquote]</blockquote>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
    "impact_story": """
HTML STRUCTURE GUIDELINES:
  - <h2>[Impact-Focused Headline]</h2>
  - <h3>The Big Picture: Key Points</h3><ul>[3 public-impact points]</ul>
  - [2-3 Paragraphs on why this matters now]
  - <h3>[The immediate impact for Americans]</h3>
  - <h3>[The economic, social, or consumer pressure point]</h3>
  - <blockquote>[Clearly attributed stakeholder analysis]</blockquote>
  - <h3>[The numbers and trends behind the story]</h3>
  - <ul>[Data, dates, affected groups, or market signals]</ul>
  - <h3>[How leaders, companies, or agencies are responding]</h3>
  - <h3>[What to watch in the next 24-72 hours]</h3>
  - <blockquote>[Second expert-analysis blockquote]</blockquote>
  - <h3>FAQ</h3>
  - <h3>Related News</h3>
""",
}

GENERATION_PROMPT = """Based on this fresh trending news topic, produce a masterful {target_words} news report designed to rank #1 on Google for its depth and authority.

Main Topic: {title}
Contextual Snippet: {snippet}
Search Category: {search_topic}
Source Freshness: {freshness}
Requested Tone: Authoritative Journalist / SEO Strategist
Article Structure: {structure_name}

{structure_instructions}

INSTRUCTIONS FOR SUCCESS:
1. START with <h2>, then <h3>The Big Picture: Key Points</h3>, then a <ul> with exactly 3 key points.
2. WRITE {target_words} WORDS of original reporting and analysis. Never submit a summary-style article.
3. USE 6-8 <h3> subsections total, excluding the main <h2>. Main subsections need 3+ substantial paragraphs.
4. INCLUDE at least two <blockquote> sections and make sure they are not fabricated direct quotes.
5. USE <strong> for important entities and <em> for emphasis throughout the body.
6. FAQ DEPTH: Include at least 5 long-tail FAQ questions that mirror Google search intent.
7. KEYWORD STRATEGY: Find the 3 most important keywords in the topic. Use the primary one in 2 subheaders and once in the first paragraph.
8. ENTITY FOCUS: Identify the main people, organizations, places, agencies, or companies involved. Use full names and titles when known.
9. HUMAN PACE: Avoid repetitive sentence starts. Mix concise impact sentences with deeper analytical paragraphs.
10. FORMAT: Use only valid article-body HTML inside content_html.

TITLE RULES:
- 55-70 characters.
- Must be a power headline: high-impact, specific, and complete.

FEATURED SCORING:
- 1-10 scale.
- Criteria: journalistic authority, SEO keyword integration, entity connection, narrative flow, and article completeness.
- score >= 8 -> "is_featured": true.

JSON OUTPUT (VALID JSON ONLY):
{{
    "title": "SEO-Optimized 55-70 char headline",
    "excerpt": "Keyword-rich 150-200 char summary",
    "content_html": "<h2>[Title]</h2><h3>The Big Picture: Key Points</h3><ul><li>[Point1]</li>...</ul><p>[Lead]...</p><h3>[Keyword-Rich Subhead]</h3>...<blockquote>[Impactful attributed analysis]</blockquote>...<h3>FAQ</h3>...<h3>Related News</h3>",
    "seo_title": "[Primary Keyword] | [Secondary Keyword] | TodaysUS",
    "seo_description": "Compelling meta description with main keyword in the first 10 words.",
    "category_slug": "politics, business, technology, etc.",
    "topics": ["entity1", "entity2", "entity3"],
    "type": "{article_type}",
    "quality_score": 10,
    "is_featured": true
}}
"""

EXPANSION_PROMPT = """This article is excellent but too short. Keep the existing content, preserve the JSON schema, and expand every section with more detail, analysis, context, and reporting texture until the article reaches about {target_words} words.

Expansion rules:
- Return valid JSON only.
- Preserve the same title unless a clearer 55-70 character title is needed.
- Keep existing facts and internal links.
- Expand each main <h3> section with 3+ substantial paragraphs.
- Add stakeholder analysis, historical context, what changed, why it matters, and what happens next.
- Include at least two <blockquote> sections, using official language or clearly labeled expert-analysis framing. Do not invent direct quotes.
- Keep at least 5 FAQ questions with concise answers.
- Use <strong> and <em> naturally in the article body.

Original source topic:
Main Topic: {title}
Contextual Snippet: {snippet}
Search Category: {search_topic}
Current Word Count: {word_count}

Draft JSON:
{draft_json}
"""

POLISH_PROMPT = """Polish this article so it satisfies the missing editorial requirements while preserving the facts, title intent, category, topics, and internal links.

Missing requirements:
{reasons}

Polish rules:
- Return valid JSON only.
- Preserve the JSON schema.
- Keep the content at or above {min_words} words.
- Ensure 6-8 <h3> subsections, excluding the main <h2>.
- Ensure at least two <blockquote> sections.
- Ensure <strong> and <em> tags appear naturally throughout the body.
- Ensure the FAQ section contains at least 5 long-tail questions in <strong> tags followed by <p> answers.
- Do not invent direct quotes.

Article JSON:
{draft_json}
"""


def generate_article(search_result: dict, internal_links: list[dict] | None = None) -> dict | None:
    """
    Call NVIDIA API to generate a full article from a search result.
    internal_links: list of {"name": str, "slug": str, "url": str}
    Returns a parsed article dict or None on failure.
    """
    if not NVIDIA_API_KEY:
        logger.error("NVIDIA_API_KEY is not set.")
        return None

    structure_name, structure_instructions = _pick_structure(search_result)
    article_type = _map_type_from_structure(structure_name)
    internal_link_hint = _build_internal_link_hint(internal_links)

    prompt = GENERATION_PROMPT.format(
        target_words=TARGET_WORDS,
        title=search_result["title"],
        snippet=search_result.get("snippet", ""),
        search_topic=search_result.get("search_topic", ""),
        freshness=search_result.get("freshness", "fresh search result"),
        structure_name=structure_name.replace("_", " ").title(),
        structure_instructions=structure_instructions,
        article_type=article_type,
    )
    if internal_link_hint:
        prompt += "\n" + internal_link_hint

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    logger.info("Generating article via NVIDIA API (structure: %s)...", structure_name)
    article_data = _request_article_json(
        messages,
        purpose=f"draft {structure_name}",
        temperature=0.72,
        max_tokens=LLM_JSON_MAX_TOKENS,
    )
    if not _has_required_fields(article_data):
        return None

    article_data.setdefault("type", article_type)
    word_count = _word_count_from_html(article_data.get("content_html", ""))
    logger.info("Draft word count: %s", word_count)

    if word_count < MIN_PUBLISH_WORDS:
        expanded = _expand_article(
            article_data=article_data,
            search_result=search_result,
            word_count=word_count,
        )
        if _has_required_fields(expanded):
            expanded_count = _word_count_from_html(expanded.get("content_html", ""))
            if expanded_count > word_count:
                logger.info("Expanded article from %s to %s words.", word_count, expanded_count)
                article_data = expanded
                word_count = expanded_count
            else:
                logger.warning("Expansion did not increase article length enough.")

    polish_reasons = _seo_polish_reasons(article_data)
    if polish_reasons:
        polished = _polish_article(article_data, polish_reasons)
        if _has_required_fields(polished):
            polished_count = _word_count_from_html(polished.get("content_html", ""))
            if polished_count >= word_count:
                logger.info("Polished article for SEO requirements: %s", ", ".join(polish_reasons))
                article_data = polished
                word_count = polished_count
            else:
                logger.warning("Polish result was shorter; keeping expanded draft.")

    final_word_count = _word_count_from_html(article_data.get("content_html", ""))
    if final_word_count < MIN_PUBLISH_WORDS:
        logger.error(
            "Generated article too short after expansion/polish: %s words. Minimum is %s.",
            final_word_count,
            MIN_PUBLISH_WORDS,
        )
        return None

    return _finalize_article(article_data, structure_name, final_word_count)


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


def _build_internal_link_hint(internal_links: list[dict] | None) -> str:
    if not internal_links:
        return ""
    links_list = "\n".join(
        f'  - "{lnk["name"]}" -> <a href="{lnk["url"]}"><u>{lnk["name"]}</u></a>'
        for lnk in internal_links[:6]
    )
    return (
        "\nINTERNAL LINKS (weave naturally into content; do not list them separately):\n"
        + links_list
        + "\nUse these contextual hyperlinks exactly as written above, including the <u> tag, within sentences where they fit naturally."
    )


def _request_article_json(
    messages: list[dict],
    *,
    purpose: str,
    temperature: float,
    max_tokens: int,
) -> dict | None:
    raw_content = _call_nvidia(messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens)
    if not raw_content:
        return None

    try:
        return _parse_json_payload(raw_content)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error during %s: %s", purpose, e)
        logger.error("Raw content (first 800 chars): %s", raw_content[:800])
        return None


def _call_nvidia(
    messages: list[dict],
    *,
    purpose: str,
    temperature: float,
    max_tokens: int,
) -> str | None:
    payload = {
        "model": NVIDIA_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.92,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("NVIDIA API %s attempt %s/%s...", purpose, attempt, MAX_RETRIES)
            resp = requests.post(
                NVIDIA_API_URL,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

        except requests.exceptions.Timeout:
            logger.warning(
                "NVIDIA API %s attempt %s/%s timed out after %ss.",
                purpose,
                attempt,
                MAX_RETRIES,
                TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            logger.error("NVIDIA API %s request error on attempt %s: %s", purpose, attempt, e)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            logger.error("NVIDIA API %s returned an unexpected response: %s", purpose, e)
            return None

        if attempt < MAX_RETRIES:
            logger.info("Retrying NVIDIA API %s...", purpose)

    logger.error("All NVIDIA API attempts failed for %s.", purpose)
    return None


def _expand_article(article_data: dict, search_result: dict, word_count: int) -> dict | None:
    prompt = EXPANSION_PROMPT.format(
        target_words=EXPANSION_TARGET_WORDS,
        title=search_result.get("title", ""),
        snippet=search_result.get("snippet", ""),
        search_topic=search_result.get("search_topic", ""),
        word_count=word_count,
        draft_json=json.dumps(article_data, ensure_ascii=False),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return _request_article_json(
        messages,
        purpose="self-expansion",
        temperature=0.65,
        max_tokens=LLM_JSON_MAX_TOKENS,
    )


def _polish_article(article_data: dict, reasons: list[str]) -> dict | None:
    prompt = POLISH_PROMPT.format(
        reasons="\n".join(f"- {reason}" for reason in reasons),
        min_words=MIN_PUBLISH_WORDS,
        draft_json=json.dumps(article_data, ensure_ascii=False),
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return _request_article_json(
        messages,
        purpose="seo polish",
        temperature=0.55,
        max_tokens=LLM_JSON_MAX_TOKENS,
    )


def _parse_json_payload(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*\n?", "", content.strip())
    content = re.sub(r"\n?```\s*$", "", content)

    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        content = json_match.group()

    content = _fix_control_chars(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return json.loads(content, strict=False)


def _fix_control_chars(s: str) -> str:
    """Escape raw newlines/tabs inside JSON strings so json.loads will not fail."""
    result = []
    in_string = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            in_string = not in_string
            result.append(ch)
        elif in_string and ch in "\n\r\t":
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _has_required_fields(article_data: dict | None) -> bool:
    if not isinstance(article_data, dict):
        logger.error("Generated article was empty or not a JSON object.")
        return False

    required = ["title", "excerpt", "content_html", "category_slug", "topics"]
    missing = [field for field in required if field not in article_data]
    if missing:
        logger.error("Missing field(s) in generated article: %s", ", ".join(missing))
        return False
    return True


def _finalize_article(article_data: dict, structure_name: str, word_count: int) -> dict:
    title = article_data["title"].strip()
    if len(title) < 40:
        logger.warning("Title too short (%s chars): '%s' - padding", len(title), title)
        title = f"{title} - What Americans Need to Know"
        article_data["title"] = title
    elif len(title) > 80:
        title = title[:77].rsplit(" ", 1)[0] + "..."
        article_data["title"] = title

    cat_slug = article_data.get("category_slug", "world")
    category = next((c for c in CATEGORIES if c["slug"] == cat_slug), CATEGORIES[2])
    article_data["category"] = category

    article_data["topics"] = _normalize_topics(article_data.get("topics", []))

    quality_score = _safe_int(article_data.get("quality_score", 0))
    is_featured = bool(article_data.get("is_featured", False)) or quality_score >= 8
    article_data["is_featured"] = is_featured
    article_data["quality_score"] = quality_score
    article_data["article_structure"] = structure_name
    article_data["word_count"] = word_count

    logger.info(
        "Generated: [%s] Q:%s/10 %s | %s | %s words",
        structure_name,
        quality_score,
        "FEATURED" if is_featured else "",
        article_data["title"],
        word_count,
    )
    return article_data


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_topics(topics: list) -> list[dict]:
    normalized = []
    for topic in topics[:5]:
        if isinstance(topic, dict):
            name = str(topic.get("name") or topic.get("slug") or "").strip()
        else:
            name = str(topic).strip()

        if not name:
            continue

        normalized.append({
            "name": name,
            "slug": name.lower().replace(" ", "-"),
        })
    return normalized


def _word_count_from_html(content_html: str) -> int:
    text = re.sub(r"<[^>]+>", " ", content_html or "")
    text = html.unescape(text)
    return len(re.findall(r"\b[\w'-]+\b", text))


def _seo_polish_reasons(article_data: dict) -> list[str]:
    content_html = article_data.get("content_html", "") or ""
    reasons = []

    h3_count = len(re.findall(r"<h3\b", content_html, re.IGNORECASE))
    if h3_count < 6:
        reasons.append(f"only {h3_count} <h3> subsections found; need 6-8")

    blockquote_count = len(re.findall(r"<blockquote\b", content_html, re.IGNORECASE))
    if blockquote_count < 2:
        reasons.append(f"only {blockquote_count} blockquote section(s) found; need at least 2")

    if not re.search(r"<strong\b", content_html, re.IGNORECASE):
        reasons.append("missing <strong> semantic emphasis tags")

    if not re.search(r"<em\b", content_html, re.IGNORECASE):
        reasons.append("missing <em> semantic emphasis tags")

    faq_count = _faq_question_count(content_html)
    if faq_count < 5:
        reasons.append(f"only {faq_count} FAQ question(s) found; need at least 5")

    return reasons


def _faq_question_count(content_html: str) -> int:
    faq_match = re.search(
        r"<h3[^>]*>\s*FAQ\s*</h3>(.*?)(?:<h3[^>]*>\s*Related\s+News\s*</h3>|$)",
        content_html,
        re.IGNORECASE | re.DOTALL,
    )
    faq_section = faq_match.group(1) if faq_match else content_html
    return len(re.findall(r"<strong[^>]*>.*?\?.*?</strong>", faq_section, re.IGNORECASE | re.DOTALL))
