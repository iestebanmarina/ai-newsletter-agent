import logging
from datetime import datetime, timedelta, timezone

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)


class BlueskyCollector(BaseCollector):
    """Collects posts from AI experts on Bluesky using the AT Protocol."""

    def __init__(self, handles: list[str]):
        self.handles = handles

    @property
    def name(self) -> str:
        return "Bluesky"

    def collect(self) -> list[Article]:
        try:
            from atproto import Client
        except ImportError:
            logger.warning("atproto not installed, skipping Bluesky collector")
            return []

        client = Client(base_url="https://public.api.bsky.app")
        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        for handle in self.handles:
            try:
                posts = self._fetch_handle(client, handle, cutoff)
                articles.extend(posts)
            except Exception:
                logger.exception(f"Error fetching Bluesky posts from @{handle}")

        logger.info(f"Bluesky collector gathered {len(articles)} posts")
        return articles

    def _fetch_handle(
        self, client, handle: str, cutoff: datetime
    ) -> list[Article]:
        articles = []

        try:
            response = client.app.bsky.feed.get_author_feed(
                {"actor": handle, "limit": 30}
            )
        except Exception:
            logger.warning(f"Could not fetch feed for @{handle}")
            return []

        for feed_item in response.feed:
            post = feed_item.post

            # Skip reposts
            if feed_item.reason is not None:
                continue

            record = post.record

            # Parse post creation time
            created_at_str = getattr(record, "created_at", None) or getattr(
                record, "createdAt", None
            )
            if not created_at_str:
                continue

            try:
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            # Skip posts older than cutoff
            if created_at < cutoff:
                continue

            # Skip posts with fewer than 10 likes
            like_count = getattr(post, "like_count", 0) or 0
            if like_count < 10:
                continue

            text = getattr(record, "text", "") or ""
            if not text.strip():
                continue

            # Build title from first 100 chars
            title = text[:100].replace("\n", " ").strip()
            if len(text) > 100:
                title += "..."

            # Build URL from post URI
            # URI format: at://did:plc:xxx/app.bsky.feed.post/yyy
            post_uri = post.uri
            post_url = f"https://bsky.app/profile/{handle}/post/{post_uri.split('/')[-1]}"

            articles.append(
                Article(
                    url=post_url,
                    title=title,
                    source=f"Bluesky @{handle}",
                    raw_content=text,
                    collected_at=created_at.replace(tzinfo=None),
                )
            )

        return articles
