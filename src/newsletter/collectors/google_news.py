import logging
from datetime import datetime
from urllib.parse import quote

import feedparser
from googlenewsdecoder import new_decoderv1

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


class GoogleNewsCollector(BaseCollector):
    """Collects articles from Google News RSS for AI-related queries."""

    def __init__(self, queries: list[str]):
        self.queries = queries

    @property
    def name(self) -> str:
        return "Google News"

    def collect(self) -> list[Article]:
        articles = []
        for query in self.queries:
            try:
                articles.extend(self._fetch_query(query))
            except Exception:
                logger.exception(f"Error fetching Google News for: {query}")
        logger.info(f"Google News collector gathered {len(articles)} articles")
        return articles

    def _fetch_query(self, query: str) -> list[Article]:
        url = GOOGLE_NEWS_RSS.format(query=quote(query))
        feed = feedparser.parse(url)
        articles = []

        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # Decode Google News redirect URL to get the real article URL
            real_url = self._decode_url(link)

            source_name = entry.get("source", {})
            if hasattr(source_name, "title"):
                source_name = source_name.title
            elif isinstance(source_name, dict):
                source_name = source_name.get("title", "Google News")
            else:
                source_name = "Google News"

            published = entry.get("published_parsed")
            collected_at = datetime(*published[:6]) if published else datetime.utcnow()

            articles.append(
                Article(
                    url=real_url,
                    title=title,
                    source=source_name,
                    collected_at=collected_at,
                )
            )

        return articles

    def _decode_url(self, google_url: str) -> str:
        """Decode a Google News redirect URL to the real article URL."""
        try:
            result = new_decoderv1(google_url)
            if result and result.get("decoded_url"):
                return result["decoded_url"]
        except Exception:
            logger.debug(f"Could not decode Google News URL: {google_url}")
        return google_url
