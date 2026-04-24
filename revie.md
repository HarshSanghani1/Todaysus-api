# Implementation Plan: Enhancing News Freshness and Article Quality

This document outlines the step-by-step technical plan to resolve the "old news" issue and the "short/low-quality article" problem in the `autoposting_agent`.

## 1. Overview of Current Issues

1.  **Freshness**: Despite using DuckDuckGo date filters, some "archived" or multi-day-old results are sneaking in.
2.  **Length & Depth**: The LLM occasionally provides a "summary" style response instead of a comprehensive 800-1000 word article, sometimes missing body content entirely.

---

## 2. Phase 1: Real-Time News Filtering

We will upgrade `web_searcher.py` to be more aggressive about timeliness.

### Step 1: Query Refinement
- Update `web_searcher.py` to append time-sensitive keywords like "latest," "breaking," and "last 24 hours" to every search query.
- For DuckDuckGo HTML, ensure the `df=d` (past day) or `df=h` (past hour) parameter is correctly parsed.

### Step 2: Date Extraction & Filtering
- Implement a regex-based date extractor to scan search snippets for relative time strings (e.g., "now," "X minutes ago," "X hours ago").
- Any result containing "year ago," "months ago," or "2021/2022/2023" will be automatically discarded before reaching the generator.

### Step 3: Google News Priority
- Prioritize Google News RSS results over DuckDuckGo scraping, as Google News is natively categorized by time and relevance.

---

## 3. Phase 2: Guaranteed Article Length (700-900 Words)

We will modify `article_generator.py` and `agent.py` to enforce strict length requirements.

### Step 1: Prompt Reinforcement
- Update the `SYSTEM_PROMPT` to explicitly state: *"If the article is under 700 words, you have failed. Use deep investigative detail, stakeholder analysis, and historical context to reach the required length."*
- Change the structure to require **at least 6-8 subsections** with 3+ paragraphs each.

### Step 2: Validation Cycle
- Modify `article_generator.py` to perform a word-count check on the response.
- If the word count is less than 600 (the absolute safety floor), the agent will trigger a "Self-Expansion" request back to the LLM.

### Step 3: The "Expander" Loop
- If the first draft is too short, send the draft back to the LLM with the instruction: *"This article is excellent but too short. Keep the existing content and expand every section with more details, quotes, and analysis to reach 900 words."*

---

## 4. Phase 3: SEO & Journalistic Structure

### Step 1: Semantic Enrichment
- Ensure the agent uses `<strong>` and `<em>` tags to highlight keywords and entities throughout the body, not just the title.
- Require at least two `<blockquote>` sections in every article to create a premium "expert opinion" look.

### Step 2: FAQ Depth
- Expand the FAQ requirement from 3 questions to 5+ questions, ensuring they cover "long-tail" search queries that users type into Google.

---

## 5. Summary of Proposed Changes (Meta-Level)

| Component | Current State | Proposed Upgrade |
| :--- | :--- | :--- |
| **web_searcher.py** | basic df=d filter | Regex-based relative time filtering (past 24h only). |
| **article_generator.py** | One-shot generation | Multi-pass generation (Draft -> Expand -> Polish). |
| **agent.py** | Length check only in logs | Loop-back length validation with retry logic. |
| **config.py** | Standard topics | Dynamic hourly-focused keywords. |

---

## 6. Next Steps

1.  Review this plan.
2.  Once approved, I will begin implementing **Phase 1 (Filtering)**.
3.  Followed by **Phase 2 (The Length Enforcer)**.
