import json
import sqlite3
import uuid
from datetime import datetime, timedelta

from .models import Article


# ---------------------------------------------------------------------------
# Newsletter history (cross-edition memory)
# ---------------------------------------------------------------------------

def init_history_table(db_path: str) -> None:
    conn = get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edition_date TEXT NOT NULL,
            subject_line TEXT,
            signal_topic TEXT,
            signal_url TEXT,
            translate_concept TEXT,
            use_this_topic TEXT,
            use_this_difficulty TEXT,
            before_after_task TEXT,
            challenge_topic TEXT,
            challenge_difficulty TEXT,
            challenge_week_number INTEGER,
            radar_urls TEXT DEFAULT '[]',
            full_json TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_history(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT edition_date, subject_line, signal_topic, signal_url,
                      translate_concept, use_this_topic, use_this_difficulty,
                      before_after_task, challenge_topic, challenge_difficulty,
                      challenge_week_number, radar_urls
               FROM newsletter_history ORDER BY id ASC"""
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def save_to_history(db_path: str, data: dict, week_number: int) -> None:
    signal = data.get("signal", {})
    translate = data.get("translate", {})
    use_this = data.get("use_this", {})
    ba = data.get("before_after", {})
    challenge = data.get("challenge", {})
    radar_urls = json.dumps([r.get("url", "") for r in data.get("radar", [])])

    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO newsletter_history
           (edition_date, subject_line, signal_topic, signal_url,
            translate_concept, use_this_topic, use_this_difficulty,
            before_after_task, challenge_topic, challenge_difficulty,
            challenge_week_number, radar_urls, full_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().strftime("%Y-%m-%d"),
            data.get("subject_line", ""),
            signal.get("headline", ""),
            signal.get("source_url", ""),
            translate.get("concept", ""),
            use_this.get("problem", ""),
            use_this.get("difficulty", "beginner"),
            ba.get("task", ""),
            challenge.get("theme", ""),
            "multi-level",
            week_number,
            radar_urls,
            json.dumps(data, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def build_history_context(history: list[dict]) -> str:
    """Build a concise summary of past editions for the prompt."""
    if not history:
        return "This is the FIRST edition. No previous newsletters exist."

    lines = [f"There have been {len(history)} previous edition(s). Here's what was covered:\n"]
    for i, h in enumerate(history, 1):
        lines.append(f"--- Edition {i} ({h['edition_date']}) ---")
        lines.append(f"  Signal: {h['signal_topic']}")
        lines.append(f"  Translate concept: {h['translate_concept']}")
        lines.append(f"  Use This: {h['use_this_topic']} ({h['use_this_difficulty']})")
        lines.append(f"  Before->After: {h['before_after_task']}")
        lines.append(f"  Challenge theme: {h['challenge_topic'][:120]}")
        lines.append("")

    concepts_covered = [h["translate_concept"] for h in history if h["translate_concept"]]
    if concepts_covered:
        lines.append(f"TRANSLATE concepts already covered: {', '.join(concepts_covered)}")

    challenge_themes = [h["challenge_topic"] for h in history if h["challenge_topic"]]
    if challenge_themes:
        lines.append(f"CHALLENGE themes already covered: {', '.join(challenge_themes)}")
    lines.append("Remember: each challenge must teach a DIFFERENT core skill from all previous editions.")

    return "\n".join(lines)


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_content TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            category TEXT DEFAULT 'uncategorized',
            relevance_score REAL DEFAULT 0.0,
            collected_at TEXT NOT NULL,
            curated INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            email TEXT PRIMARY KEY,
            subscribed_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            estimated_cost_usd REAL NOT NULL,
            step TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT,
            recipient TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_newsletters (
            id TEXT PRIMARY KEY,
            pipeline_run_id TEXT,
            subject TEXT NOT NULL,
            html_content TEXT NOT NULL,
            json_data TEXT DEFAULT '',
            linkedin_post TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            sent_at TEXT
        )
    """)
    # Add linkedin_post column if upgrading from older schema
    try:
        conn.execute("ALTER TABLE pending_newsletters ADD COLUMN linkedin_post TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add multi-dimensional scoring columns
    for col in [
        "impact_score REAL DEFAULT 0.0",
        "actionability_score REAL DEFAULT 0.0",
        "source_quality_score REAL DEFAULT 0.0",
        "recency_bonus REAL DEFAULT 0.0",
        "final_score REAL DEFAULT 0.0",
    ]:
        try:
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edition_date TEXT NOT NULL,
            subject_line TEXT,
            signal_topic TEXT,
            signal_url TEXT,
            translate_concept TEXT,
            use_this_topic TEXT,
            use_this_difficulty TEXT,
            before_after_task TEXT,
            challenge_topic TEXT,
            challenge_difficulty TEXT,
            challenge_week_number INTEGER,
            radar_urls TEXT DEFAULT '[]',
            full_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_seconds REAL,
            articles_collected INTEGER DEFAULT 0,
            articles_curated INTEGER DEFAULT 0,
            articles_sent INTEGER DEFAULT 0,
            emails_sent INTEGER DEFAULT 0,
            emails_failed INTEGER DEFAULT 0,
            error_message TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def insert_article(db_path: str, article: Article) -> bool:
    """Insert an article. Returns True if inserted, False if duplicate."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO articles
               (url, title, source, raw_content, summary, category,
                relevance_score, collected_at, curated, sent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                article.url,
                article.title,
                article.source,
                article.raw_content,
                article.summary,
                article.category,
                article.relevance_score,
                article.collected_at.isoformat(),
                int(article.curated),
                int(article.sent),
            ),
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def insert_articles(db_path: str, articles: list[Article]) -> int:
    """Insert multiple articles. Returns count of newly inserted."""
    count = 0
    for article in articles:
        if insert_article(db_path, article):
            count += 1
    return count


def get_uncurated_articles(db_path: str) -> list[Article]:
    """Get articles that haven't been curated yet."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM articles WHERE curated = 0 AND sent = 0"
    ).fetchall()
    conn.close()
    return [_row_to_article(r) for r in rows]


def get_articles_for_newsletter(
    db_path: str,
    limit: int = 20,
    max_same_source: int = 5,
    min_papers: int = 2,
    min_expert: int = 1,
) -> list[Article]:
    """Get curated, unsent articles with diversity-aware selection.

    Selection rules:
    1. Top overall article reserved for Signal
    2. Max `max_same_source` from any single source
    3. Min `min_papers` research papers (HF/arXiv) if available
    4. Min `min_expert` expert voice (Bluesky/expert blogs) if available
    5. Fill remainder by score
    """
    import logging
    _logger = logging.getLogger(__name__)

    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE curated = 1 AND sent = 0
           ORDER BY CASE WHEN final_score > 0 THEN final_score ELSE relevance_score END DESC"""
    ).fetchall()
    conn.close()

    all_articles = [_row_to_article(r) for r in rows]
    if not all_articles:
        return []

    paper_sources = {"Hugging Face Papers", "arXiv"}
    expert_prefixes = ("Bluesky @",)
    expert_feeds = {
        "karpathy.substack.com", "drfeifei.substack.com",
        "interconnects.ai", "simonwillison.net",
        "lilianweng.github.io", "lexfridman.com",
    }

    def _is_paper(a: Article) -> bool:
        return a.source in paper_sources

    def _is_expert(a: Article) -> bool:
        if any(a.source.startswith(p) for p in expert_prefixes):
            return True
        return any(feed in a.source.lower() for feed in expert_feeds)

    selected: list[Article] = []
    selected_urls: set[str] = set()
    source_counts: dict[str, int] = {}

    def _can_add(a: Article) -> bool:
        if a.url in selected_urls:
            return False
        if source_counts.get(a.source, 0) >= max_same_source:
            return False
        return True

    def _add(a: Article) -> None:
        selected.append(a)
        selected_urls.add(a.url)
        source_counts[a.source] = source_counts.get(a.source, 0) + 1

    # 1. Reserve top article for Signal
    if all_articles:
        _add(all_articles[0])

    # 2. Fill paper slots
    papers_added = sum(1 for a in selected if _is_paper(a))
    for a in all_articles:
        if papers_added >= min_papers:
            break
        if _is_paper(a) and _can_add(a):
            _add(a)
            papers_added += 1

    # 3. Fill expert slots
    experts_added = sum(1 for a in selected if _is_expert(a))
    for a in all_articles:
        if experts_added >= min_expert:
            break
        if _is_expert(a) and _can_add(a):
            _add(a)
            experts_added += 1

    # 4. Fill remainder by score
    for a in all_articles:
        if len(selected) >= limit:
            break
        if _can_add(a):
            _add(a)

    if papers_added < min_papers:
        _logger.info(f"Diversity: only {papers_added}/{min_papers} papers available")
    if experts_added < min_expert:
        _logger.info(f"Diversity: only {experts_added}/{min_expert} expert posts available")

    return selected


def update_article_curation(
    db_path: str,
    url: str,
    summary: str,
    category: str,
    relevance_score: float,
    impact_score: float = 0.0,
    actionability_score: float = 0.0,
    source_quality_score: float = 0.0,
    recency_bonus: float = 0.0,
    final_score: float = 0.0,
) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """UPDATE articles
           SET summary = ?, category = ?, relevance_score = ?,
               impact_score = ?, actionability_score = ?,
               source_quality_score = ?, recency_bonus = ?,
               final_score = ?, curated = 1
           WHERE url = ?""",
        (summary, category, relevance_score,
         impact_score, actionability_score,
         source_quality_score, recency_bonus,
         final_score, url),
    )
    conn.commit()
    conn.close()


def update_article_content(db_path: str, url: str, raw_content: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE articles SET raw_content = ? WHERE url = ?",
        (raw_content, url),
    )
    conn.commit()
    conn.close()


def mark_as_sent(db_path: str, urls: list[str]) -> None:
    conn = get_connection(db_path)
    conn.executemany(
        "UPDATE articles SET sent = 1 WHERE url = ?",
        [(url,) for url in urls],
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Pending newsletters
# ---------------------------------------------------------------------------

def save_pending_newsletter(
    db_path: str, run_id: str, subject: str, html: str, json_data: str = ""
) -> str:
    """Save a pending newsletter. Returns the newsletter id."""
    newsletter_id = uuid.uuid4().hex[:12]
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO pending_newsletters
           (id, pipeline_run_id, subject, html_content, json_data, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
        (newsletter_id, run_id, subject, html, json_data, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return newsletter_id


def get_pending_newsletter(db_path: str) -> dict | None:
    """Get the most recent pending newsletter, or None."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT id, pipeline_run_id, subject, html_content, json_data, status, created_at, sent_at
           FROM pending_newsletters
           WHERE status = 'pending'
           ORDER BY created_at DESC
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def mark_newsletter_sent(db_path: str, newsletter_id: str) -> None:
    """Mark a pending newsletter as sent."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE pending_newsletters SET status = 'sent', sent_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), newsletter_id),
    )
    conn.commit()
    conn.close()


def save_linkedin_post(db_path: str, newsletter_id: str, post_text: str) -> None:
    """Save a LinkedIn post for a newsletter."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE pending_newsletters SET linkedin_post = ? WHERE id = ?",
        (post_text, newsletter_id),
    )
    conn.commit()
    conn.close()


def delete_pending_newsletter(db_path: str, newsletter_id: str) -> bool:
    """Delete a pending newsletter. Only deletes if status is 'pending'. Returns True if deleted."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM pending_newsletters WHERE id = ? AND status = 'pending'",
            (newsletter_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_linkedin_post(db_path: str, newsletter_id: str) -> str | None:
    """Get the LinkedIn post for a newsletter. Returns None if newsletter not found."""
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT linkedin_post FROM pending_newsletters WHERE id = ?",
        (newsletter_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return row["linkedin_post"]


def get_pending_newsletters(db_path: str, limit: int = 10) -> list[dict]:
    """Get pending newsletters (without html_content for performance)."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT id, subject, created_at, status
           FROM pending_newsletters
           WHERE status = 'pending'
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_newsletters(db_path: str, limit: int = 5) -> list[dict]:
    """Get the most recent sent newsletters (without html_content for performance)."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT id, subject, created_at, sent_at
           FROM pending_newsletters
           WHERE status = 'sent'
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_newsletter_by_id(db_path: str, newsletter_id: str) -> dict | None:
    """Get a single newsletter by id, including html_content."""
    conn = get_connection(db_path)
    row = conn.execute(
        """SELECT id, pipeline_run_id, subject, html_content, json_data,
                  status, created_at, sent_at
           FROM pending_newsletters
           WHERE id = ?""",
        (newsletter_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def add_subscriber(db_path: str, email: str) -> bool:
    """Add a subscriber. Reactivates if previously unsubscribed. Returns True if new or reactivated."""
    conn = get_connection(db_path)
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute("SELECT active FROM subscribers WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO subscribers (email, subscribed_at, active) VALUES (?, ?, 1)",
                (email, now),
            )
            conn.commit()
            return True
        elif row["active"] == 0:
            conn.execute(
                "UPDATE subscribers SET active = 1, subscribed_at = ? WHERE email = ?",
                (now, email),
            )
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_active_subscribers(db_path: str) -> list[str]:
    """Get all active subscriber emails."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT email FROM subscribers WHERE active = 1"
    ).fetchall()
    conn.close()
    return [row["email"] for row in rows]


def remove_subscriber(db_path: str, email: str) -> bool:
    """Mark a subscriber as inactive. Returns True if found and deactivated."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "UPDATE subscribers SET active = 0 WHERE email = ? AND active = 1",
            (email,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API usage / cost tracking
# ---------------------------------------------------------------------------

MODEL_PRICING = {
    # (input $/M tokens, output $/M tokens)
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a Claude API call."""
    for key, (inp_price, out_price) in MODEL_PRICING.items():
        if key in model:
            return (input_tokens * inp_price + output_tokens * out_price) / 1_000_000
    # Fallback to Sonnet pricing
    return (input_tokens * 3.00 + output_tokens * 15.00) / 1_000_000


def log_api_usage(
    db_path: str,
    *,
    pipeline_run_id: str = "",
    model: str,
    input_tokens: int,
    output_tokens: int,
    step: str = "",
) -> None:
    cost = estimate_cost(model, input_tokens, output_tokens)
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO api_usage
           (pipeline_run_id, model, input_tokens, output_tokens, estimated_cost_usd, step, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pipeline_run_id, model, input_tokens, output_tokens, cost, step, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def log_email_send(
    db_path: str,
    *,
    pipeline_run_id: str = "",
    recipient: str,
    status: str,
    error_message: str = "",
) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO email_log
           (pipeline_run_id, recipient, status, error_message, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (pipeline_run_id, recipient, status, error_message, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Pipeline run tracking
# ---------------------------------------------------------------------------

def cleanup_stale_runs(db_path: str, max_minutes: int = 15) -> int:
    """Mark pipeline runs stuck in 'running' for too long as failed. Returns count."""
    cutoff = (datetime.utcnow() - timedelta(minutes=max_minutes)).isoformat()
    conn = get_connection(db_path)
    cursor = conn.execute(
        """UPDATE pipeline_runs
           SET status = 'failed',
               finished_at = ?,
               error_message = 'Auto-failed: stuck in running for over ' || ? || ' minutes'
           WHERE status = 'running' AND started_at < ?""",
        (datetime.utcnow().isoformat(), str(max_minutes), cutoff),
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def create_pipeline_run(db_path: str) -> str:
    """Create a new pipeline run record. Returns the run id."""
    run_id = uuid.uuid4().hex[:12]
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO pipeline_runs (id, status, started_at) VALUES (?, 'running', ?)",
        (run_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return run_id


def update_pipeline_run(db_path: str, run_id: str, **kwargs) -> None:
    """Update fields on a pipeline run. Accepts any column name as kwarg."""
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values())
    vals.append(run_id)
    conn = get_connection(db_path)
    conn.execute(f"UPDATE pipeline_runs SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Dashboard queries
# ---------------------------------------------------------------------------

def get_subscriber_stats(db_path: str, env_subscribers: list[str] | None = None) -> dict:
    conn = get_connection(db_path)
    db_active = conn.execute("SELECT COUNT(*) FROM subscribers WHERE active = 1").fetchone()[0]
    db_emails = set(
        r[0] for r in conn.execute("SELECT email FROM subscribers WHERE active = 1").fetchall()
    )
    last_7 = conn.execute(
        "SELECT COUNT(*) FROM subscribers WHERE active = 1 AND subscribed_at >= ?",
        ((datetime.utcnow() - timedelta(days=7)).isoformat(),),
    ).fetchone()[0]
    conn.close()
    env_set = set(env_subscribers) if env_subscribers else set()
    total = len(db_emails | env_set)
    return {"active": total, "db_only": db_active, "env_only": len(env_set - db_emails), "last_7_days": last_7}


def get_article_stats(db_path: str) -> dict:
    conn = get_connection(db_path)
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    curated = conn.execute("SELECT COUNT(*) FROM articles WHERE curated = 1").fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM articles WHERE sent = 1").fetchone()[0]
    by_source = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM articles GROUP BY source ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    by_category = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM articles WHERE curated = 1 GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "curated": curated,
        "sent": sent,
        "by_source": [{"source": r[0], "count": r[1]} for r in by_source],
        "by_category": [{"category": r[0], "count": r[1]} for r in by_category],
    }


def get_api_usage_stats(db_path: str) -> dict:
    conn = get_connection(db_path)
    total_cost = conn.execute("SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM api_usage").fetchone()[0]
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0).isoformat()
    monthly_cost = conn.execute(
        "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM api_usage WHERE created_at >= ?",
        (month_start,),
    ).fetchone()[0]
    total_tokens = conn.execute(
        "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM api_usage"
    ).fetchone()
    by_run = conn.execute(
        """SELECT pipeline_run_id, SUM(estimated_cost_usd) as cost, SUM(input_tokens) as inp, SUM(output_tokens) as out
           FROM api_usage WHERE pipeline_run_id != ''
           GROUP BY pipeline_run_id ORDER BY rowid DESC LIMIT 10"""
    ).fetchall()
    conn.close()
    return {
        "total_cost_usd": round(total_cost, 4),
        "monthly_cost_usd": round(monthly_cost, 4),
        "total_input_tokens": total_tokens[0],
        "total_output_tokens": total_tokens[1],
        "by_run": [{"run_id": r[0], "cost": round(r[1], 4), "input_tokens": r[2], "output_tokens": r[3]} for r in by_run],
    }


def get_email_stats(db_path: str) -> dict:
    conn = get_connection(db_path)
    total_sent = conn.execute("SELECT COUNT(*) FROM email_log WHERE status = 'sent'").fetchone()[0]
    total_failed = conn.execute("SELECT COUNT(*) FROM email_log WHERE status = 'failed'").fetchone()[0]
    recent = conn.execute(
        "SELECT recipient, status, error_message, created_at FROM email_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {
        "total_sent": total_sent,
        "total_failed": total_failed,
        "recent": [{"recipient": r[0], "status": r[1], "error": r[2], "created_at": r[3]} for r in recent],
    }


def get_pipeline_runs(db_path: str, limit: int = 20) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _row_to_article(row: sqlite3.Row) -> Article:
    d = dict(row)
    return Article(
        url=d["url"],
        title=d["title"],
        source=d["source"],
        raw_content=d["raw_content"],
        summary=d["summary"],
        category=d["category"],
        relevance_score=d["relevance_score"],
        impact_score=d.get("impact_score", 0.0),
        actionability_score=d.get("actionability_score", 0.0),
        source_quality_score=d.get("source_quality_score", 0.0),
        recency_bonus=d.get("recency_bonus", 0.0),
        final_score=d.get("final_score", 0.0),
        collected_at=datetime.fromisoformat(d["collected_at"]),
        curated=bool(d["curated"]),
        sent=bool(d["sent"]),
    )
