import json
import sqlite3
from datetime import datetime, timedelta

from .models import Article


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


def get_articles_for_newsletter(db_path: str, limit: int = 20) -> list[Article]:
    """Get curated, unsent articles sorted by relevance score."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE curated = 1 AND sent = 0
           ORDER BY relevance_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [_row_to_article(r) for r in rows]


def update_article_curation(
    db_path: str,
    url: str,
    summary: str,
    category: str,
    relevance_score: float,
) -> None:
    conn = get_connection(db_path)
    conn.execute(
        """UPDATE articles
           SET summary = ?, category = ?, relevance_score = ?, curated = 1
           WHERE url = ?""",
        (summary, category, relevance_score, url),
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


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        url=row["url"],
        title=row["title"],
        source=row["source"],
        raw_content=row["raw_content"],
        summary=row["summary"],
        category=row["category"],
        relevance_score=row["relevance_score"],
        collected_at=datetime.fromisoformat(row["collected_at"]),
        curated=bool(row["curated"]),
        sent=bool(row["sent"]),
    )
