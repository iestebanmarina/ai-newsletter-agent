import json
import logging
from typing import Any

import anthropic

from .config import settings
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

2. **Scores** (all 0.0 to 1.0 unless noted):
   - **relevance**: How relevant and interesting this is for an AI-focused audience (0.0-1.0)
   - **impact**: Breakthrough vs incremental. Major paradigm shifts=0.9+, significant=0.7, incremental=0.3-0.5 (0.0-1.0)
   - **actionability**: Can readers act on this now? Practical tools/techniques=0.8+, theoretical=0.2 (0.0-1.0)
   - **source_quality**: Research paper=0.9+, Expert blog=0.8, Major news outlet=0.6, Reddit/forum=0.4 (0.0-1.0)
   - **recency_bonus**: Extra credit for very fresh news. Breaking/today=0.2, this week=0.1, older=0.0 (0.0-0.2)

3. **summary**: A concise 2-3 sentence summary capturing the key takeaway. Write in a professional, engaging tone.

Respond with a JSON array of objects, one per article. Each object must have: "url", "category", "relevance", "impact", "actionability", "source_quality", "recency_bonus", "summary"."""

CURATION_SYSTEM_PROMPT_ES = """Eres un curador de noticias de IA para una newsletter semanal en español. Tu trabajo es analizar artículos y proporcionar metadatos estructurados para cada uno.

Para cada artículo debes devolver:
1. **category**: Una de: opinion, forum, report, future, success_case, uncategorized
   - opinion: Artículos de opinión, editoriales, análisis, comentarios
   - forum: Debates comunitarios, hilos de Reddit, posts en foros
   - report: Artículos de investigación, informes del sector, benchmarks, anuncios técnicos
   - future: Artículos prospectivos, predicciones, exploraciones teóricas
   - success_case: Implementaciones reales de IA, casos de estudio, despliegues en producción
   - uncategorized: No encaja en las otras categorías

2. **Puntuaciones** (todas de 0.0 a 1.0 salvo indicación):
   - **relevance**: Qué tan relevante e interesante es para una audiencia enfocada en IA (0.0-1.0)
   - **impact**: Rupturista vs. incremental. Cambios de paradigma=0.9+, significativo=0.7, incremental=0.3-0.5 (0.0-1.0)
   - **actionability**: ¿Puede el lector actuar sobre esto ahora? Herramientas prácticas=0.8+, teórico=0.2 (0.0-1.0)
   - **source_quality**: Paper de investigación=0.9+, Blog experto=0.8, Medio de referencia=0.6, Reddit/foro=0.4 (0.0-1.0)
   - **recency_bonus**: Crédito extra por noticias muy recientes. Hoy=0.2, esta semana=0.1, más antiguo=0.0 (0.0-0.2)

3. **summary**: Un resumen conciso de 2-3 frases que capture el mensaje clave. Escribe en español, con tono directo y concreto. Sin jerga técnica innecesaria. Si el artículo es en inglés, resume en español igualmente.

Responde con un array JSON de objetos, uno por artículo. Cada objeto debe tener: "url", "category", "relevance", "impact", "actionability", "source_quality", "recency_bonus", "summary"."""

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
    ctx_len = settings.curation_context_length
    for a in articles:
        content = a.raw_content[:ctx_len] if a.raw_content else "(no content scraped)"
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

    active_prompt = CURATION_SYSTEM_PROMPT_ES if settings.newsletter_style == "spanish" else CURATION_SYSTEM_PROMPT

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=active_prompt,
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
            article.summary = data.get("summary", "")

            # Multi-dimensional scores
            relevance = float(data.get("relevance", data.get("relevance_score", 0.0)))
            impact = float(data.get("impact", 0.0))
            actionability = float(data.get("actionability", 0.0))
            source_quality = float(data.get("source_quality", 0.0))
            recency_bonus = float(data.get("recency_bonus", 0.0))

            final_score = (
                relevance * 0.35
                + impact * 0.25
                + actionability * 0.20
                + source_quality * 0.15
                + recency_bonus * 0.05
            )

            article.relevance_score = final_score
            article.impact_score = impact
            article.actionability_score = actionability
            article.source_quality_score = source_quality
            article.recency_bonus = recency_bonus
            article.final_score = final_score
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
