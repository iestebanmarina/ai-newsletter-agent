# Knowledge in Chain - AI Newsletter Agent

## Overview

Automated weekly AI newsletter system. Collects articles from RSS/Google News/Reddit/HuggingFace/Bluesky, curates with Claude, generates a structured 6-section newsletter (Signal, Radar, Translate, Use This, Before→After, Challenge), and sends via Resend email API. Includes a FastAPI web server with public landing page, admin dashboard, and scheduled pipeline automation.

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
    huggingface.py - HuggingFace daily papers feed
    bluesky.py   - Bluesky social posts from AI experts
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
uv run newsletter --dry-run        # Full pipeline without sending email (saves to pending, not history)
uv run newsletter --schedule       # Run scheduler only (no web server)
uv run newsletter                  # Full pipeline: collect, curate, generate, send to all

# Dependencies
uv sync                            # Install/sync dependencies from lock file
```

## Pipeline Modes

The pipeline has 4 modes. The scheduler uses `preview` + `send-pending`. The others are manual.

### preview (Saturday automatic, or `--preview`)

Generates a newsletter for review before sending. This is the first half of the weekly flow.

1. Collect articles from all sources (RSS, Google News, Reddit, HuggingFace, Bluesky)
2. Scrape full content via HTTP (BeautifulSoup)
3. Curate with Claude (categorize, score, summarize — batches of 10)
4. Select top 20 articles with diversity rules (max per source, min papers, min expert)
5. Generate newsletter JSON with Claude (6 sections) → Jinja2 renders HTML
6. Generate LinkedIn promotion post with Claude
7. Save as `pending_newsletter` (status='pending') + send preview to `REVIEW_EMAIL`

Does NOT save to `newsletter_history`. The newsletter stays as pending until sent or deleted.

### send-pending (Monday automatic, or `--send-pending`)

Sends the most recent pending newsletter to all subscribers. This is the second half of the weekly flow.

1. Find most recent `pending_newsletter` with status='pending'
2. Gather all subscribers (env vars + DB)
3. Send to all via Resend API (personalized unsubscribe links per subscriber)
4. Mark newsletter as 'sent'
5. **Save to `newsletter_history`** (only after successful email delivery)

Does NOT generate anything. Only sends what was already created by preview.

### dry-run (`--dry-run` or dashboard "Dry Run" button)

Runs the full generation pipeline without sending emails. For testing.

1. Steps 1-6 same as preview (collect, scrape, curate, select, generate, LinkedIn)
2. Save to `pending_newsletters` and immediately mark as 'sent' (archived)
3. Save a backup of `newsletter_history` to `newsletter_history_backup_YYYYMMDD_HHMMSS.json`

Does NOT save to `newsletter_history`. Does NOT send emails.

### full (`uv run newsletter` without flags)

Legacy/manual mode. Generates AND sends in one step, bypassing the preview-review-send workflow.

1. Steps 1-6 same as preview
2. Send to ALL subscribers
3. Mark articles as sent
4. Archive newsletter as 'sent'
5. **Save to `newsletter_history`** (only after successful email delivery)

### History rule

**`newsletter_history` only contains editions that were actually sent to subscribers.** Preview and dry-run never write to it. Send-pending and full mode write to it only after emails are successfully delivered.

## Weekly Production Flow

```
Saturday 09:00 UTC ─── scheduler runs mode="preview"
  │
  ├── Collects ~100-200 articles from 7+ sources
  ├── Claude curates and scores articles
  ├── Selects top 20 with source diversity
  ├── Claude generates 6-section newsletter + LinkedIn post
  ├── Saves as pending_newsletter (status='pending')
  └── Sends preview email to REVIEW_EMAIL
         │
         ▼
  Admin reviews preview email
  Admin opens dashboard (knowledgeinchain.com/dashboard):
    ├── Edit: change edition number/date (re-renders HTML from stored JSON)
    ├── Delete: discard if not satisfactory
    └── Approve: do nothing, wait for Monday
         │
         ▼
Monday 09:00 UTC ─── scheduler runs mode="send-pending"
  │
  ├── Finds most recent pending newsletter
  ├── Sends to all subscribers via Resend
  ├── Marks as 'sent'
  └── Saves to newsletter_history (cross-edition memory for Claude)
```

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
| PATCH | `/api/dashboard/pending-newsletters/{id}` | Edit edition number/date (re-renders HTML) |
| DELETE | `/api/dashboard/pending-newsletters/{id}` | Delete a pending newsletter (only if status=pending) |
| GET | `/api/dashboard/newsletter-history` | List all edition history entries |
| DELETE | `/api/dashboard/newsletter-history/{id}` | Delete a history entry |
| POST | `/api/dashboard/trigger-pipeline` | Trigger pipeline (mode: dry-run/preview/send-pending) |

## Database Tables (SQLite, WAL mode)

| Table | Purpose |
|-------|---------|
| `articles` | Collected articles (URL as PK, with multi-dimensional curation scores) |
| `subscribers` | Email subscribers (with active/inactive soft delete) |
| `pending_newsletters` | Generated newsletters (pending → sent). Stores HTML, JSON data, LinkedIn post |
| `newsletter_history` | Cross-edition memory. Only contains editions sent to subscribers. Used to calculate edition number and prevent Claude from repeating topics |
| `api_usage` | Claude API cost tracking (tokens + estimated USD per call, per pipeline step) |
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
- History only written after successful email delivery to subscribers
- Articles categorized as: opinion, forum, report, future, success_case, uncategorized
- Multi-dimensional article scoring: relevance (0.35), impact (0.25), actionability (0.20), source quality (0.15), recency bonus (0.05)
- Diversity-aware article selection: max per source, min papers, min expert posts
- Cookie-based dashboard auth with SHA-256 token generation
- Per-subscriber personalized unsubscribe links in every email
