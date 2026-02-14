# Knowledge in Chain - AI Newsletter Agent

## Overview

Automated weekly AI newsletter system. Collects articles from RSS/Google News/Reddit, curates with Claude, generates a structured 6-section newsletter (Signal, Radar, Translate, Use This, Before→After, Challenge), and sends via Resend email API. Includes a FastAPI web server with public landing page, admin dashboard, and scheduled pipeline automation.

## Architecture

```
src/newsletter/
  __init__.py    - Package initialization
  __main__.py    - Module entry point
  main.py        - CLI entry point, pipeline orchestration, scheduler
  web.py         - FastAPI server (landing, dashboard, API, health check)
  config.py      - Pydantic settings (env vars + .env file)
  db.py          - SQLite database (articles, subscribers, pipeline runs, history, costs)
  models.py      - Pydantic models (Article, Newsletter, Category enum)
  curator.py     - Claude-powered article categorization, scoring, summarization
  generator.py   - Newsletter generation with Claude + Jinja2 templates
  emailer.py     - Resend email sending with per-subscriber unsubscribe links
  linkedin.py    - LinkedIn post generation via Claude
  collectors/
    base.py      - Abstract BaseCollector interface
    rss.py       - RSS feed parser (feedparser)
    google_news.py - Google News RSS with URL decoding
    reddit.py    - Reddit API collector (PRAW)
    scraper.py   - HTTP content extraction (BeautifulSoup + lxml)
  templates/
    newsletter.html  - Email template (6-section dark theme layout)
    landing.html     - Public landing page with subscription form + archive
    dashboard.html   - Admin dashboard (stats, pipeline runs, newsletter management)
    unsubscribe.html - Unsubscribe confirmation page
```

## Commands

```bash
# Run locally (always use uv, never py/python directly)
uv run newsletter --serve          # Web server + scheduler on port 8080
uv run newsletter --preview        # Generate newsletter, send preview to REVIEW_EMAIL
uv run newsletter --send-pending   # Send latest pending newsletter to all subscribers
uv run newsletter --dry-run        # Full pipeline without sending email
uv run newsletter --schedule       # Run scheduler only (no web server)
uv run newsletter                  # Full pipeline: collect, curate, generate, send

# Dependencies
uv sync                            # Install/sync dependencies from lock file
```

## Pipeline Flow

1. **Collect** — RSS + Google News + Reddit collectors fetch articles
2. **Scrape** — Fetch full article content via HTTP (BeautifulSoup)
3. **Curate** — Claude scores, categorizes, summarizes articles (batched, 10 at a time)
4. **Select** — Pick top N articles by relevance score (default 20)
5. **Generate** — Claude generates 6-section newsletter JSON → Jinja2 renders HTML
6. **LinkedIn** — Claude generates LinkedIn promotion post
7. **Send/Save** — Based on mode: save as pending (preview), send to all (full), or send pending (send-pending)

## Web Endpoints

### Public
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Landing page with subscription form + recent newsletters |
| POST | `/api/subscribe` | Add subscriber (validates email, reactivates if unsubscribed) |
| GET | `/api/unsubscribe?email=` | Unsubscribe confirmation page |
| GET | `/newsletter/{id}` | View archived newsletter HTML |
| GET | `/newsletter/{id}/linkedin` | Get LinkedIn post for a newsletter |
| GET | `/health` | Health check (`ok` / `degraded` + scheduler status) |

### Dashboard (auth-protected if DASHBOARD_PASSWORD set)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/dashboard` | Admin dashboard HTML |
| POST | `/dashboard/login` | Password login → cookie token |
| GET | `/api/dashboard/subscribers` | Subscriber stats |
| GET | `/api/dashboard/articles` | Article stats (by source, by category) |
| GET | `/api/dashboard/api-costs` | API usage & cost breakdown |
| GET | `/api/dashboard/emails` | Email send stats + recent logs |
| GET | `/api/dashboard/pipeline-runs` | Last 20 pipeline runs with metrics |
| GET | `/api/dashboard/pending-newsletters` | List pending newsletters |
| DELETE | `/api/dashboard/pending-newsletters/{id}` | Delete a pending newsletter (only if status=pending) |
| POST | `/api/dashboard/trigger-pipeline` | Trigger pipeline (mode: dry-run/preview/send-pending) |

## Database Tables (SQLite, WAL mode)

| Table | Purpose |
|-------|---------|
| `articles` | Collected articles (URL as PK, with curation fields) |
| `subscribers` | Email subscribers (with active/inactive soft delete) |
| `pending_newsletters` | Generated newsletters awaiting send (pending → sent) |
| `newsletter_history` | Cross-edition memory to prevent repeated topics |
| `api_usage` | Claude API cost tracking (tokens + estimated USD per call) |
| `email_log` | Email delivery log (sent/failed per recipient) |
| `pipeline_runs` | Full audit trail of each pipeline execution |

## Deployment

- **Platform**: Railway (knowledgeinchain.com via Cloudflare/GoDaddy DNS)
- **Docker**: Multi-stage build with uv, runs `uv run newsletter --serve`
- **Database**: SQLite on Railway Volume mounted at `/data` (DATABASE_PATH=/data/newsletter.db)
- **Schedule**: Preview on Saturday 09:00 UTC, Send on Monday 09:00 UTC
- **Health check**: `GET /health` — returns scheduler thread status
- **Auto-fail**: Pipeline runs stuck in "running" >15 minutes are auto-failed on next run

## Key Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| ANTHROPIC_API_KEY | Yes | Claude API key for curation + generation |
| RESEND_API_KEY | Yes | Resend email API key |
| NEWSLETTER_FROM_EMAIL | Yes | Sender email (must be verified in Resend) |
| BASE_URL | Yes | Public URL for unsubscribe links (https://knowledgeinchain.com) |
| CLAUDE_MODEL | No | Model for curation/generation (default: claude-sonnet-4-5-20250929) |
| NEWSLETTER_SUBSCRIBERS | No | Comma-separated subscriber emails (merged with DB subscribers) |
| REVIEW_EMAIL | No | Email for preview sends |
| DASHBOARD_PASSWORD | No | Dashboard auth (empty = open access) |
| DATABASE_PATH | No | SQLite path (default: newsletter.db, Railway: /data/newsletter.db) |
| MAX_ARTICLES_PER_NEWSLETTER | No | Article limit per edition (default: 20) |
| PREVIEW_SCHEDULE_DAY | No | Day for preview (default: saturday) |
| PREVIEW_SCHEDULE_TIME | No | Time for preview (default: 09:00) |
| SEND_SCHEDULE_DAY | No | Day for send (default: monday) |
| SEND_SCHEDULE_TIME | No | Time for send (default: 09:00) |
| REDDIT_CLIENT_ID | No | Reddit API credentials |
| REDDIT_CLIENT_SECRET | No | Reddit API credentials |

## Conventions

- Python 3.11, managed with uv (uv.lock for reproducible builds)
- Pydantic for settings and data models; Pydantic Settings for config
- FastAPI for web server, Uvicorn as ASGI server
- SQLite with WAL mode for concurrent reads
- Jinja2 for all HTML templates (newsletter email, landing, dashboard, unsubscribe)
- All API costs tracked in `api_usage` table with per-model pricing
- Newsletter history tracked for cross-edition memory (no repeated topics/concepts)
- Articles categorized as: opinion, forum, report, future, success_case, uncategorized
- Cookie-based dashboard auth with SHA-256 token generation
- Per-subscriber personalized unsubscribe links in every email
