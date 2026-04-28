# Autoposting Hallucination Fix Plan

## Problem

The autoposting agent currently gives the model only a search result title, a short snippet, and a broad search topic. The prompt then asks for an 800-1000 word authoritative report with entities, quotes, data, and analysis. That mismatch pushes the model to invent unsupported details.

## Root Cause

- `web_searcher.py` extracts only result titles and snippets from DuckDuckGo or Google News RSS.
- The selected result URL is not preserved for grounding or attribution.
- The source article body is not fetched before generation.
- `article_generator.py` asks for a long, high-authority article even when the factual input is only one or two lines.
- There is no validation step that stops generation when source text is too thin.

## Fix Strategy

1. Capture source URLs from search results.
2. Fetch and extract readable text from the selected article page.
3. Pass source title, source URL, snippet, and extracted source text into the model prompt.
4. Require the model to use only facts supported by the source material.
5. Ban fabricated quotes, invented statistics, invented expert names, and unrelated context.
6. Lower model temperature to reduce creative drift.
7. Refuse generation when source content is below a minimum word count.
8. Save source metadata in the generated article object for debugging.

## Implementation Notes

- Use only existing dependencies plus Python standard library helpers.
- Avoid adding a heavy scraping package unless the existing lightweight extractor is insufficient.
- Keep the pipeline behavior simple: if source extraction fails or returns too little text, skip that cycle instead of publishing a low-grounding article.
- Preserve the existing JSON output shape expected by `publisher.py`.

## Acceptance Criteria

- Search results include `source_url` when available.
- Selected result includes `source_text` and `source_word_count`.
- Generation is blocked if `source_word_count` is too low.
- Prompt explicitly grounds the article in source material.
- Generated article metadata includes source URL and source word count.
- Python modules compile successfully.

## Local Test Commands

- Scrape only, no model call and no publish:
  `python -m autoposting_agent.run_once --scrape-only`
- Scrape one exact source URL, no model call and no publish:
  `python -m autoposting_agent.run_once --scrape-only --url "https://www.todaysjob.in/tpsc-assistant-technical-officer-post/"`
- Full scrape plus generation check, no publish:
  `python -m autoposting_agent.run_once --dry-run`
- Full generation check from one exact source URL, no publish:
  `python -m autoposting_agent.run_once --dry-run --url "https://www.todaysjob.in/tpsc-assistant-technical-officer-post/"`
- Real scheduled/cron behavior, including publish:
  `python -m autoposting_agent.run_once`
