import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

import schedule

from .collectors.google_news import GoogleNewsCollector
from .collectors.reddit import RedditCollector
from .collectors.rss import RSSCollector
from .collectors.scraper import scrape_article_content
from .config import settings
from .curator import curate_articles
from .db import (
    get_active_subscribers,
    get_articles_for_newsletter,
    get_uncurated_articles,
    init_db,
    insert_articles,
    mark_as_sent,
    update_article_content,
    update_article_curation,
)
from .emailer import send_newsletter
from .generator import generate_newsletter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline(dry_run: bool = False) -> None:
    """Execute the full newsletter pipeline."""
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is required. Set it in .env or environment.")
        sys.exit(1)

    db_path = settings.database_path
    init_db(db_path)

    # Step 1: Collect articles from all sources
    logger.info("=== Step 1: Collecting articles ===")
    all_articles = []

    collectors = [
        RSSCollector(feed_urls=settings.rss_feeds),
        GoogleNewsCollector(queries=settings.google_news_queries),
        RedditCollector(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            subreddits=settings.reddit_subreddits,
        ),
    ]

    for collector in collectors:
        try:
            articles = collector.collect()
            all_articles.extend(articles)
            logger.info(f"  {collector.name}: {len(articles)} articles")
        except Exception:
            logger.exception(f"  {collector.name}: failed")

    new_count = insert_articles(db_path, all_articles)
    logger.info(f"Stored {new_count} new articles ({len(all_articles)} total collected)")

    # Step 2: Scrape full content for articles missing it
    logger.info("=== Step 2: Scraping article content ===")
    uncurated = get_uncurated_articles(db_path)
    scraped = 0
    for article in uncurated:
        if not article.raw_content or len(article.raw_content) < 100:
            content = scrape_article_content(article.url)
            if content:
                update_article_content(db_path, article.url, content)
                article.raw_content = content
                scraped += 1
    logger.info(f"Scraped content for {scraped} articles")

    # Step 3: Curate with Claude
    logger.info("=== Step 3: Curating articles with Claude ===")
    uncurated = get_uncurated_articles(db_path)
    if uncurated:
        curated = curate_articles(
            uncurated,
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
        )
        for article in curated:
            if article.curated:
                update_article_curation(
                    db_path,
                    url=article.url,
                    summary=article.summary,
                    category=article.category,
                    relevance_score=article.relevance_score,
                )
        logger.info(f"Curated {len(curated)} articles")
    else:
        logger.info("No uncurated articles to process")

    # Step 4: Select top articles
    logger.info("=== Step 4: Selecting top articles ===")
    top_articles = get_articles_for_newsletter(
        db_path, limit=settings.max_articles_per_newsletter
    )
    logger.info(f"Selected {len(top_articles)} articles for newsletter")

    if not top_articles:
        logger.warning("No articles available for newsletter, aborting")
        return

    # Step 5: Generate newsletter
    logger.info("=== Step 5: Generating newsletter ===")
    newsletter = generate_newsletter(
        top_articles,
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
    )

    # Save HTML preview
    preview_path = Path("newsletter_preview.html")
    preview_path.write_text(newsletter.html_content, encoding="utf-8")
    logger.info(f"Newsletter preview saved to {preview_path.resolve()}")

    # Step 6: Send email
    if dry_run:
        logger.info("=== Dry run: skipping email send ===")
    else:
        logger.info("=== Step 6: Sending newsletter ===")
        # Merge subscribers from env var and database (union, no duplicates)
        env_subscribers = set(settings.subscriber_list)
        db_subscribers = set(get_active_subscribers(db_path))
        all_subscribers = sorted(env_subscribers | db_subscribers)
        logger.info(f"Sending to {len(all_subscribers)} subscribers ({len(env_subscribers)} env, {len(db_subscribers)} db)")

        success = send_newsletter(
            html_content=newsletter.html_content,
            from_email=settings.newsletter_from_email,
            subscribers=all_subscribers,
            api_key=settings.resend_api_key,
            base_url=settings.base_url,
        )
        if success:
            mark_as_sent(db_path, [a.url for a in top_articles])
            logger.info("Newsletter sent successfully!")
        else:
            logger.error("Newsletter sending failed or partially failed")


def start_scheduler_thread() -> threading.Thread:
    """Launch the scheduler in a daemon thread. Returns the thread."""
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    return t


def run_scheduler() -> None:
    """Run the pipeline on a weekly schedule."""
    day = settings.schedule_day.lower()
    time_str = settings.schedule_time

    scheduler_map = {
        "monday": schedule.every().monday,
        "tuesday": schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday": schedule.every().thursday,
        "friday": schedule.every().friday,
        "saturday": schedule.every().saturday,
        "sunday": schedule.every().sunday,
    }

    job = scheduler_map.get(day)
    if job is None:
        logger.error(f"Invalid schedule day: {day}")
        sys.exit(1)

    job.at(time_str).do(run_pipeline)
    logger.info(f"Scheduler started: will run every {day} at {time_str}")

    while True:
        schedule.run_pending()
        time.sleep(60)


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="newsletter",
        description="AI Newsletter Agent - Collect, curate, and send AI news",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline without sending email",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a weekly schedule instead of once",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start web server with landing page + scheduler",
    )

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        from .web import app

        port = int(os.environ.get("PORT", "8080"))
        logger.info(f"Starting web server on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port)
    elif args.schedule:
        run_scheduler()
    else:
        run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    cli()
