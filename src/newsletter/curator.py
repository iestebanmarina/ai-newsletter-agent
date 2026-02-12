import json
import logging
from typing import Any

import anthropic

from .db import log_api_usage
from .models import Article, Category

logger = logging.getLogger(__name__)

# Module-level pipeline context (set by main.py before calling curate_articles)
_current_db_path: str = ""
_current_run_id: str = ""


def set_pipeline_context(db_path: str, run_id: str) -> None:
    global _current_db_path, _current_run_id
    _current_db_path = db_path
    _current_run_id = run_id

CURATION_SYSTEM_PROMPT = """You are an AI news curator for a weekly newsletter. Your job is to analyze articles and provide structured metadata for each one.

For each article, you must return:
1. **category**: One of: opinion, forum, report, future, success_case, uncategorized
   - opinion: Opinion pieces, editorials, analysis, commentary
   - forum: Community discussions, Reddit threads, forum posts
   - report: Research papers, industry reports, benchmark results, technical announcements
   - future: Forward-looking pieces, predictions, theoretical explorations
   - success_case: Real-world AI implementations, case studies, production deployments
   - uncategorized: Doesn't fit other categories

2. **relevance_score**: 0.0 to 1.0 rating of how relevant and interesting this is for an AI-focused audience
   - 1.0: Major breakthrough, paradigm shift, must-read
   - 0.7-0.9: Very interesting, significant development
   - 0.4-0.6: Moderately interesting, niche but valuable
   - 0.1-0.3: Minor news, tangentially related
   - 0.0: Not relevant to AI

3. **summary**: A concise 2-3 sentence summary capturing the key takeaway. Write in a professional, engaging tone.

Respond with a JSON array of objects, one per article. Each object must have: "url", "category", "relevance_score", "summary"."""

BATCH_SIZE = 10


def curate_articles(
    articles: list[Article],
    api_key: str,
    model: str,
) -> list[Article]:
    """Use Claude to categorize, score, and summarize articles."""
    if not articles:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    curated = []

    # Process in batches
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]
        try:
            results = _curate_batch(client, model, batch)
            curated.extend(results)
        except Exception:
            logger.exception(f"Error curating batch starting at index {i}")
            # Keep articles uncurated rather than losing them
            curated.extend(batch)

    logger.info(f"Curated {len(curated)} articles")
    return curated


def _curate_batch(
    client: anthropic.Anthropic,
    model: str,
    articles: list[Article],
) -> list[Article]:
    """Send a batch of articles to Claude for curation."""
    articles_data = []
    for a in articles:
        content = a.raw_content[:2000] if a.raw_content else "(no content scraped)"
        articles_data.append({
            "url": a.url,
            "title": a.title,
            "source": a.source,
            "content_preview": content,
        })

    user_message = (
        "Analyze and curate the following articles. "
        "Return a JSON array with one object per article.\n\n"
        f"Articles:\n{json.dumps(articles_data, indent=2)}"
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=CURATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    if _current_db_path:
        try:
            log_api_usage(
                _current_db_path,
                pipeline_run_id=_current_run_id,
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                step="curation",
            )
        except Exception:
            logger.debug("Failed to log API usage", exc_info=True)

    response_text = response.content[0].text
    parsed = _parse_json_response(response_text)

    # Map results back to articles
    result_map: dict[str, dict[str, Any]] = {}
    for item in parsed:
        if isinstance(item, dict) and "url" in item:
            result_map[item["url"]] = item

    curated = []
    for article in articles:
        if article.url in result_map:
            data = result_map[article.url]
            article.category = data.get("category", Category.UNCATEGORIZED)
            article.relevance_score = float(data.get("relevance_score", 0.0))
            article.summary = data.get("summary", "")
            article.curated = True
        curated.append(article)

    return curated


def _parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from Claude's response, handling markdown code blocks."""
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from Claude response")
    return []
