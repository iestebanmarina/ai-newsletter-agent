# Knowledge in Chain - AI Newsletter Agent

## Overview

Automated weekly AI newsletter system. Collects articles from RSS/Google News/Reddit, curates with Claude, generates a structured 6-section newsletter, and sends via Resend email API.

## Architecture

```
src/newsletter/
  main.py        - CLI entry point, pipeline orchestration, scheduler
  web.py         - FastAPI server (landing, dashboard, API, health check)
  config.py      - Pydantic settings (env vars + .env file)
  db.py          - SQLite database (articles, subscribers, pipeline runs, history)
  models.py      - Pydantic models (Article, Newsletter)
  collector/     - Article collectors (RSS, Google News, Reddit)
  curator.py     - Claude-powered article curation
  generator.py   - Newsletter generation with Claude + Jinja2 templates
  emailer.py     - Resend email sending with per-subscriber unsubscribe links
  linkedin.py    - LinkedIn post generation
  templates/     - Jinja2 HTML templates (newsletter, landing, dashboard, unsubscribe)
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

## Deployment

- **Platform**: Railway (knowledgeinchain.com via Cloudflare/GoDaddy DNS)
- **Docker**: Multi-stage build with uv, runs `uv run newsletter --serve`
- **Database**: SQLite on Railway Volume mounted at `/data` (DATABASE_PATH=/data/newsletter.db)
- **Schedule**: Preview on Saturday 09:00 UTC, Send on Monday 09:00 UTC
- **Health check**: `GET /health` - returns scheduler thread status

## Key Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| ANTHROPIC_API_KEY | Yes | Claude API key for curation + generation |
| RESEND_API_KEY | Yes | Resend email API key |
| NEWSLETTER_FROM_EMAIL | Yes | Sender email (must be verified in Resend) |
| NEWSLETTER_SUBSCRIBERS | No | Comma-separated subscriber emails (+ DB subscribers) |
| REVIEW_EMAIL | No | Email for preview sends |
| DASHBOARD_PASSWORD | No | Dashboard auth (empty = open access) |
| BASE_URL | Yes | Public URL for unsubscribe links (https://knowledgeinchain.com) |
| DATABASE_PATH | No | SQLite path (default: newsletter.db, Railway: /data/newsletter.db) |
| PREVIEW_SCHEDULE_DAY | No | Day for preview (default: saturday) |
| PREVIEW_SCHEDULE_TIME | No | Time for preview (default: 09:00) |
| SEND_SCHEDULE_DAY | No | Day for send (default: monday) |
| SEND_SCHEDULE_TIME | No | Time for send (default: 09:00) |

## Conventions

- Python 3.11, managed with uv (uv.lock for reproducible builds)
- Pydantic for settings and models
- FastAPI for web server
- SQLite with WAL mode for concurrent reads
- All API costs tracked in `api_usage` table
- Newsletter history tracked for cross-edition memory (no repeated topics)
