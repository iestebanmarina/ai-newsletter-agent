# Knowledge in Chain - AI Newsletter Agent

Automated weekly AI newsletter system. Collects articles from 7+ sources, curates with Claude, generates a structured 6-section newsletter, and sends via Resend. Includes a FastAPI web server with public landing page, admin dashboard, and scheduled pipeline automation.

**Live:** [knowledgeinchain.com](https://knowledgeinchain.com)

## Weekly Flow

```
Saturday 09:00 UTC ── preview mode
  │  Collect articles from all sources
  │  Claude curates, scores, and selects top 20
  │  Generate 6-section newsletter + LinkedIn post
  │  Save as pending → send preview to REVIEW_EMAIL
  │
  ▼
Admin reviews in dashboard
  │  Edit edition number, date, editor's note
  │  Delete and re-run if needed
  │
  ▼
Monday 09:00 UTC ── send-pending mode
     Send to all subscribers via Resend
     Save to newsletter history
```

## Newsletter Sections

**Part 1 -- Inform:**
1. **Signal** -- The single most important AI story this week, explained simply.
2. **Translate** -- One technical concept from the news, explained with an everyday analogy.
3. **Radar** -- Quick takes on the stories shaping the AI landscape right now.

**Part 2 -- Practice:**
4. **Prompt Lab** -- A ready-to-use prompt you can copy, paste, and adapt.
5. **Workflow Shift** -- A common task reimagined with AI, shown side by side.
6. **Weekly Challenge** -- A hands-on exercise at three levels.

## Sources

| Source | Collector | Description |
|--------|-----------|-------------|
| RSS feeds (11) | `rss.py` | MIT Tech Review, The Verge, Ars Technica, OpenAI, Anthropic, DeepMind, Meta AI, Netflix Tech, Spotify Eng, LangChain, HAI Stanford |
| Expert RSS (9) | `rss.py` | Latent Space, Exponential View, Pragmatic Engineer, and more |
| Google News | `google_news.py` | Queries for AI news with URL decoding |
| Reddit | `reddit.py` | r/artificial, r/MachineLearning, r/LocalLLaMA |
| HuggingFace | `huggingface.py` | Daily papers feed |
| Bluesky | `bluesky.py` | Posts from AI experts |
| Editor Picks | `editor_picks.py` | Manually curated URLs via dashboard |

## Setup

### Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/)

### Installation

```bash
git clone git@github.com:iestebanmarina/ai-newsletter-agent.git
cd ai-newsletter-agent
uv sync
cp .env.example .env  # fill in your API keys
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `RESEND_API_KEY` | Yes | Resend email API key |
| `NEWSLETTER_FROM_EMAIL` | Yes | Sender email (verified domain in Resend) |
| `BASE_URL` | Yes | Public URL for unsubscribe links |
| `REVIEW_EMAIL` | No | Email for preview and dry-run sends |
| `DASHBOARD_PASSWORD` | No | Dashboard auth (empty = open access) |
| `REDDIT_CLIENT_ID` | No | Reddit API credentials |
| `REDDIT_CLIENT_SECRET` | No | Reddit API credentials |
| `CLAUDE_MODEL` | No | Default: `claude-sonnet-4-5-20250929` |
| `DATABASE_PATH` | No | Default: `newsletter.db` |
| `MAX_ARTICLES_PER_NEWSLETTER` | No | Default: `20` |
| `PREVIEW_SCHEDULE_DAY` | No | Default: `saturday` |
| `PREVIEW_SCHEDULE_TIME` | No | Default: `09:00` |
| `SEND_SCHEDULE_DAY` | No | Default: `monday` |
| `SEND_SCHEDULE_TIME` | No | Default: `09:00` |

## Usage

```bash
# Web server + scheduler (production mode)
uv run newsletter --serve

# Generate preview, send to REVIEW_EMAIL
uv run newsletter --preview

# Send latest pending newsletter to all subscribers
uv run newsletter --send-pending

# Full pipeline test (saves as pending, sends [TEST] to REVIEW_EMAIL)
uv run newsletter --dry-run

# Full pipeline: generate and send to all (legacy, bypasses review flow)
uv run newsletter
```

## Project Structure

```
src/newsletter/
├── main.py              # CLI entry point, pipeline orchestration, scheduler
├── web.py               # FastAPI server (landing, dashboard, API, health check)
├── config.py            # Pydantic settings (env vars + .env)
├── db.py                # SQLite database (articles, subscribers, history, costs)
├── models.py            # Pydantic models (Article, Newsletter, Category)
├── curator.py           # Claude-powered article categorization and scoring
├── generator.py         # Newsletter generation with Claude + Jinja2
├── emailer.py           # Resend email sending with per-subscriber unsubscribe links
├── linkedin.py          # LinkedIn post generation via Claude
├── collectors/
│   ├── base.py          # Abstract BaseCollector interface
│   ├── rss.py           # RSS feed parser (feedparser)
│   ├── google_news.py   # Google News RSS with URL decoding
│   ├── reddit.py        # Reddit API collector (PRAW)
│   ├── huggingface.py   # HuggingFace daily papers feed
│   ├── bluesky.py       # Bluesky social posts from AI experts
│   ├── editor_picks.py  # Editor-curated URLs from dashboard
│   └── scraper.py       # HTTP content extraction (BeautifulSoup + lxml)
└── templates/
    ├── newsletter.html  # Email template (6-section dark theme)
    ├── landing.html     # Public landing page with subscription form + archive
    ├── dashboard.html   # Admin dashboard (stats, pipeline, newsletter management)
    └── unsubscribe.html # Unsubscribe confirmation page
scripts/
├── fix_email_via_api.py     # Update subscriber email via API
└── retry_failed_emails.py   # Retry failed email deliveries
```

## Deployment

- **Platform:** [Railway](https://railway.app) with custom domain via Cloudflare DNS
- **Docker:** Multi-stage build with uv, runs `uv run newsletter --serve`
- **Database:** SQLite on Railway Volume mounted at `/data`
- **Health check:** `GET /health` returns scheduler thread status

## License

[MIT](LICENSE)
