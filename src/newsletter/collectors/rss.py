import logging
from datetime import datetime

import feedparser

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collects articles from configured RSS feeds."""

    def __init__(self, feed_urls: list[str]):
        self.feed_urls = feed_urls

    @property
    def name(self) -> str:
        return "RSS Feeds"

    def collect(self) -> list[Article]:
        articles = []
        for url in self.feed_urls:
            try:
                articles.extend(self._parse_feed(url))
            except Exception:
                logger.exception(f"Error parsing RSS feed: {url}")
        logger.info(f"RSS collector gathered {len(articles)} articles")
        return articles

    def _parse_feed(self, feed_url: str) -> list[Article]:
        feed = feedparser.parse(feed_url)
        source = feed.feed.get("title", feed_url)
        articles = []

        for entry in feed.entries[:15]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            published = entry.get("published_parsed") or entry.get("updated_parsed")
            collected_at = datetime(*published[:6]) if published else datetime.utcnow()

            content = ""
            if hasattr(entry, "summary"):
                content = entry.summary
            elif hasattr(entry, "content"):
                content = entry.content[0].value if entry.content else ""

            articles.append(
                Article(
                    url=link,
                    title=title,
                    source=source,
                    raw_content=content,
                    collected_at=collected_at,
                )
            )

        return articles
