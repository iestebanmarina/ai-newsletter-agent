import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic
from jinja2 import Environment, FileSystemLoader

from .models import Article, Category, CATEGORY_DISPLAY, Newsletter, NewsletterSection

logger = logging.getLogger(__name__)

EDITORIAL_SYSTEM_PROMPT = """You are the editor of a weekly AI newsletter called "AI Weekly Digest".
Write a brief editorial introduction (3-5 sentences) for this week's newsletter.

You'll receive a summary of the top articles. Your intro should:
- Highlight the biggest theme or story of the week
- Briefly mention 1-2 other notable trends
- Be engaging, professional, and concise
- Avoid hype and buzzwords; prefer substantive, insightful observations
- Do NOT use markdown formatting; write in plain text suitable for HTML

Return ONLY the editorial text, nothing else."""

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_newsletter(
    articles: list[Article],
    api_key: str,
    model: str,
) -> Newsletter:
    """Generate a complete newsletter from curated articles."""
    # Group articles into sections by category
    sections = _build_sections(articles)

    # Generate editorial intro via Claude
    client = anthropic.Anthropic(api_key=api_key)
    intro = _generate_editorial(client, model, articles)

    # Render HTML
    html = _render_html(intro, sections)

    newsletter = Newsletter(
        date=datetime.utcnow(),
        intro_editorial=intro,
        sections=sections,
        html_content=html,
    )

    logger.info(f"Generated newsletter with {len(articles)} articles in {len(sections)} sections")
    return newsletter


def _build_sections(articles: list[Article]) -> list[NewsletterSection]:
    """Group articles into sections by category."""
    by_category: dict[str, list[Article]] = {}
    for article in articles:
        cat = article.category
        by_category.setdefault(cat, []).append(article)

    # Order sections in a logical reading flow
    category_order = [
        Category.REPORT,
        Category.OPINION,
        Category.SUCCESS_CASE,
        Category.FUTURE,
        Category.FORUM,
        Category.UNCATEGORIZED,
    ]

    sections = []
    for cat in category_order:
        cat_articles = by_category.get(cat.value, []) or by_category.get(cat, [])
        if cat_articles:
            # Sort by relevance within each section
            cat_articles.sort(key=lambda a: a.relevance_score, reverse=True)
            sections.append(
                NewsletterSection(
                    category=cat,
                    display_name=CATEGORY_DISPLAY.get(cat, cat.value.replace("_", " ").title()),
                    articles=cat_articles,
                )
            )

    return sections


def _generate_editorial(
    client: anthropic.Anthropic,
    model: str,
    articles: list[Article],
) -> str:
    """Generate an editorial intro using Claude."""
    # Prepare a compact summary of articles for the prompt
    summaries = []
    for a in articles[:15]:
        summaries.append(f"- [{a.source}] {a.title}: {a.summary}")
    articles_text = "\n".join(summaries)

    today = datetime.utcnow().strftime("%B %d, %Y")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=EDITORIAL_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Date: {today}\n\n"
                        f"This week's top articles:\n{articles_text}\n\n"
                        "Write the editorial introduction."
                    ),
                }
            ],
        )
        return response.content[0].text.strip()
    except Exception:
        logger.exception("Failed to generate editorial intro")
        return "Welcome to this week's AI Weekly Digest, your curated roundup of the most important developments in artificial intelligence."


def _render_html(intro: str, sections: list[NewsletterSection]) -> str:
    """Render the newsletter HTML using the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("newsletter.html")

    today = datetime.utcnow().strftime("%B %d, %Y")

    return template.render(
        subject=f"AI Weekly Digest - {today}",
        date=today,
        intro=intro,
        sections=sections,
    )
