import logging
from datetime import datetime

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)


class EditorPicksCollector(BaseCollector):
    """Collector that reads manually curated URLs from the editor_picks table.

    Articles from this collector are marked with source_quality_score=1.0 so
    they survive the diversity selection and appear in the newsletter.
    The curation step will still run on them (to generate summaries/scores),
    but their source_quality starts at maximum.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @property
    def name(self) -> str:
        return "Editor Picks"

    def collect(self) -> list[Article]:
        # Import here to avoid circular imports (db imports models)
        from ..db import get_editor_picks

        picks = get_editor_picks(self._db_path, unused_only=True)
        articles: list[Article] = []

        for pick in picks:
            url = pick.get("url", "").strip()
            if not url:
                continue
            article = Article(
                url=url,
                title=pick.get("title") or url,
                source="Editor Pick",
                raw_content=pick.get("editor_note", ""),
                summary=pick.get("editor_note", ""),
                category="uncategorized",
                relevance_score=0.95,
                source_quality_score=1.0,
                final_score=0.95,
                collected_at=datetime.utcnow(),
            )
            articles.append(article)

        logger.info(f"Editor picks: loaded {len(articles)} curated URL(s)")
        return articles
