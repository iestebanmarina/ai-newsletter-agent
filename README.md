# AI Newsletter Agent

AI-powered weekly newsletter agent that automatically collects, curates, and delivers AI news. It aggregates content from multiple sources, uses Claude to analyze and categorize articles, and generates a professionally formatted HTML email.

## How it works

```
1. COLLECT     → RSS feeds, Google News, Reddit
2. SCRAPE      → Extract full article content
3. CURATE      → Claude categorizes, scores, and summarizes
4. SELECT      → Top 20 articles by relevance
5. GENERATE    → Claude writes editorial intro + HTML rendering
6. SEND        → Email delivery via Resend
```

## Setup

### Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
git clone git@github.com:iestebanmarina/ai-newsletter-agent.git
cd ai-newsletter-agent
uv sync
```

### Configuration

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key from [console.anthropic.com](https://console.anthropic.com) |
| `RESEND_API_KEY` | Yes | Email service key from [resend.com](https://resend.com) |
| `NEWSLETTER_FROM_EMAIL` | Yes | Sender email (must match a verified domain in Resend) |
| `NEWSLETTER_SUBSCRIBERS` | Yes | Comma-separated list of recipient emails |
| `REDDIT_CLIENT_ID` | No | Reddit API credentials from [reddit.com/prefs/apps](https://reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | No | Reddit API secret |
| `CLAUDE_MODEL` | No | Defaults to `claude-sonnet-4-5-20250929` |
| `MAX_ARTICLES_PER_NEWSLETTER` | No | Defaults to `20` |
| `SCHEDULE_DAY` | No | Defaults to `monday` |
| `SCHEDULE_TIME` | No | Defaults to `09:00` |
| `DATABASE_PATH` | No | Defaults to `newsletter.db` |

## Usage

```bash
# Run the full pipeline once (dry run, no email sent)
uv run newsletter --dry-run

# Run the full pipeline and send emails
uv run newsletter

# Run on a weekly schedule
uv run newsletter --schedule
```

The `--dry-run` flag generates the newsletter and saves it to `newsletter_preview.html` without sending any emails.

## Default sources

**RSS Feeds:** MIT Technology Review, The Verge AI, Ars Technica, OpenAI Blog, Anthropic Blog, DeepMind Blog, Meta AI Blog

**Google News queries:** "artificial intelligence", "AI implementation enterprise", "machine learning breakthrough"

**Reddit subreddits:** r/artificial, r/MachineLearning, r/LocalLLaMA (requires Reddit API credentials)

## Project structure

```
src/newsletter/
├── main.py              # CLI and pipeline orchestration
├── config.py            # Configuration (loads from .env)
├── models.py            # Data models (Article, Newsletter, Category)
├── db.py                # SQLite database operations
├── curator.py           # Claude-powered article curation
├── generator.py         # Newsletter generation with Claude editorial
├── emailer.py           # Email delivery via Resend
├── collectors/
│   ├── base.py          # Abstract collector base class
│   ├── rss.py           # RSS feed collector
│   ├── google_news.py   # Google News collector
│   ├── reddit.py        # Reddit collector
│   └── scraper.py       # Web content scraper
└── templates/
    └── newsletter.html  # Jinja2 email template
```

## License

MIT
