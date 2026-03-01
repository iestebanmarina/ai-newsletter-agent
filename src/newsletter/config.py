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
    newsletter_style: str = "english"  # "english" | "spanish"

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
        # Engineering blogs: how companies actually deploy AI, not press releases
        "https://netflixtechblog.com/feed",
        "https://engineering.atspotify.com/feed/",
        "https://blog.langchain.dev/rss/",
        # Research / policy: different angle from tech press
        "https://hai.stanford.edu/news/rss.xml",
    ]

    # Expert RSS feeds (blogs, substacks, podcasts)
    expert_rss_feeds: list[str] = [
        "https://karpathy.substack.com/feed",
        "https://drfeifei.substack.com/feed",
        "https://www.interconnects.ai/feed",
        "https://simonwillison.net/atom/everything/",
        "https://lilianweng.github.io/index.xml",
        "https://lexfridman.com/feed/podcast/",
        # Practitioner Substacks: strategic + practitioner angle
        "https://www.latent.space/feed",
        "https://www.exponentialview.co/feed",
        "https://newsletter.pragmaticengineer.com/feed",
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

    # Hugging Face Papers
    huggingface_enabled: bool = True
    huggingface_feed_url: str = "https://papers.takara.ai/api/feed"

    # Bluesky
    bluesky_enabled: bool = True
    bluesky_handles: list[str] = [
        "yolanda.gil.bsky.social",
        "emollick.bsky.social",
        "timnitgebru.bsky.social",
        "jackclark.bsky.social",
    ]

    # Curation
    curation_context_length: int = 5000

    # Diversity-aware selection
    max_articles_same_source: int = 5
    min_papers_per_newsletter: int = 2
    min_expert_per_newsletter: int = 1

    @property
    def subscriber_list(self) -> list[str]:
        if not self.newsletter_subscribers:
            return []
        return [s.strip() for s in self.newsletter_subscribers.split(",") if s.strip()]


settings = Settings()
