from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250929"

    # Reddit API
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "ai-newsletter-agent/0.1"

    # Resend
    resend_api_key: str = ""

    # Newsletter
    newsletter_from_email: str = "newsletter@example.com"
    newsletter_subscribers: str = ""

    # DB
    database_path: str = "newsletter.db"

    # Web
    base_url: str = "http://localhost:8080"

    # Dashboard
    dashboard_password: str = ""

    # Pipeline
    max_articles_per_newsletter: int = 20

    # Review
    review_email: str = ""

    # Scheduler
    preview_schedule_day: str = "saturday"
    preview_schedule_time: str = "09:00"
    send_schedule_day: str = "monday"
    send_schedule_time: str = "09:00"

    # RSS feeds
    rss_feeds: list[str] = [
        "https://www.technologyreview.com/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://blog.openai.com/rss/",
        "https://www.anthropic.com/feed",
        "https://deepmind.google/blog/rss.xml",
        "https://ai.meta.com/blog/rss/",
    ]

    # Google News queries
    google_news_queries: list[str] = [
        "artificial intelligence",
        "AI implementation enterprise",
        "machine learning breakthrough",
    ]

    # Reddit subreddits
    reddit_subreddits: list[str] = [
        "artificial",
        "MachineLearning",
        "LocalLLaMA",
    ]

    @property
    def subscriber_list(self) -> list[str]:
        if not self.newsletter_subscribers:
            return []
        return [s.strip() for s in self.newsletter_subscribers.split(",") if s.strip()]


settings = Settings()
