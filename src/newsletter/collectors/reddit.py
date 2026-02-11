import logging
from datetime import datetime

import praw

from ..models import Article
from .base import BaseCollector

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """Collects top posts from AI-related subreddits."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: list[str],
    ):
        self.subreddits = subreddits
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

    @property
    def name(self) -> str:
        return "Reddit"

    def collect(self) -> list[Article]:
        if not self.client_id or not self.client_secret:
            logger.warning("Reddit credentials not configured, skipping")
            return []

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
        )

        articles = []
        for sub_name in self.subreddits:
            try:
                articles.extend(self._fetch_subreddit(reddit, sub_name))
            except Exception:
                logger.exception(f"Error fetching r/{sub_name}")

        logger.info(f"Reddit collector gathered {len(articles)} articles")
        return articles

    def _fetch_subreddit(self, reddit: praw.Reddit, sub_name: str) -> list[Article]:
        subreddit = reddit.subreddit(sub_name)
        articles = []

        for post in subreddit.top(time_filter="week", limit=10):
            # Skip low-engagement posts
            if post.score < 50:
                continue

            url = post.url
            # For self-posts, use the Reddit permalink
            if post.is_self:
                url = f"https://reddit.com{post.permalink}"

            content = post.selftext[:3000] if post.is_self else ""

            articles.append(
                Article(
                    url=url,
                    title=post.title,
                    source=f"r/{sub_name}",
                    raw_content=content,
                    collected_at=datetime.utcfromtimestamp(post.created_utc),
                )
            )

        return articles
