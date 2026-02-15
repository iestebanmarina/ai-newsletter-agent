import logging
from datetime import datetime

import feedparser

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)


class HuggingFaceCollector(BaseCollector):
    """Collects trending papers from Hugging Face via community RSS feed."""

    def __init__(self, feed_url: str):
        self.feed_url = feed_url

    @property
    def name(self) -> str:
        return "Hugging Face Papers"

    def collect(self) -> list[Article]:
        try:
            return self._parse_feed()
        except Exception:
            logger.exception("Error fetching Hugging Face papers feed")
            return []

    def _parse_feed(self) -> list[Article]:
        feed = feedparser.parse(self.feed_url)
        articles = []

        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            published = entry.get("published_parsed") or entry.get("updated_parsed")
            collected_at = datetime(*published[:6]) if published else datetime.utcnow()

            # Use summary/abstract as raw_content
            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "content"):
                content = entry.content[0].value if entry.content else ""

            articles.append(
                Article(
                    url=link,
                    title=title,
                    source="Hugging Face Papers",
                    raw_content=content,
                    collected_at=collected_at,
                )
            )

        logger.info(f"Hugging Face collector gathered {len(articles)} papers")
        return articles
