import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import schedule

from .collectors.google_news import GoogleNewsCollector
from .collectors.reddit import RedditCollector
from .collectors.rss import RSSCollector
from .collectors.scraper import scrape_article_content
from .config import settings
from .curator import curate_articles
from .curator import set_pipeline_context as set_curator_context
from .db import (
    create_pipeline_run,
    get_active_subscribers,
    get_articles_for_newsletter,
    get_pending_newsletter,
    get_uncurated_articles,
    init_db,
    insert_articles,
    mark_as_sent,
    mark_newsletter_sent,
    save_linkedin_post,
    save_pending_newsletter,
    update_article_content,
    update_article_curation,
    update_pipeline_run,
)
from .emailer import send_newsletter
from .generator import generate_newsletter
from .generator import set_pipeline_context as set_generator_context
from .linkedin import generate_linkedin_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline(dry_run: bool = False, mode: str = "full") -> None:
    """Execute the newsletter pipeline.

    Modes:
      - "full": collect, curate, generate, send to all subscribers (original behaviour)
      - "preview": collect, curate, generate, save as pending, send ONLY to review_email
      - "send-pending": skip generation, send most recent pending newsletter to all subscribers
    """
    db_path = settings.database_path
    init_db(db_path)

    # ------------------------------------------------------------------
    # mode = send-pending: send the latest pending newsletter
    # ------------------------------------------------------------------
    if mode == "send-pending":
        logger.info("=== Send-pending mode: sending saved newsletter ===")
        pending = get_pending_newsletter(db_path)
        if pending is None:
            logger.warning("No pending newsletter found, nothing to send")
            return

        env_subscribers = set(settings.subscriber_list)
        db_subscribers = set(get_active_subscribers(db_path))
        all_subscribers = sorted(env_subscribers | db_subscribers)
        logger.info(f"Sending pending newsletter {pending['id']} to {len(all_subscribers)} subscribers")

        email_result = send_newsletter(
            html_content=pending["html_content"],
            from_email=settings.newsletter_from_email,
            subscribers=all_subscribers,
            api_key=settings.resend_api_key,
            base_url=settings.base_url,
            db_path=db_path,
            pipeline_run_id=pending.get("pipeline_run_id", ""),
            subject=pending["subject"],
        )

        if email_result["sent"] > 0:
            mark_newsletter_sent(db_path, pending["id"])
            logger.info(f"Newsletter sent: {email_result['sent']} ok, {email_result['failed']} failed")
        else:
            logger.error("Newsletter sending failed")
        return

    # ------------------------------------------------------------------
    # mode = full | preview: run the generation pipeline
    # ------------------------------------------------------------------
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is required. Set it in .env or environment.")
        sys.exit(1)

    # Create pipeline run and set context on curator/generator
    run_id = create_pipeline_run(db_path)
    set_curator_context(db_path, run_id)
    set_generator_context(db_path, run_id)
    logger.info(f"Pipeline run {run_id} started (mode={mode})")

    start_time = time.time()

    try:
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
        update_pipeline_run(db_path, run_id, articles_collected=len(all_articles))

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
        curated_count = 0
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
                    curated_count += 1
            logger.info(f"Curated {curated_count} articles")
        else:
            logger.info("No uncurated articles to process")
        update_pipeline_run(db_path, run_id, articles_curated=curated_count)

        # Step 4: Select top articles
        logger.info("=== Step 4: Selecting top articles ===")
        top_articles = get_articles_for_newsletter(
            db_path, limit=settings.max_articles_per_newsletter
        )
        logger.info(f"Selected {len(top_articles)} articles for newsletter")

        if not top_articles:
            logger.warning("No articles available for newsletter, aborting")
            duration = time.time() - start_time
            update_pipeline_run(
                db_path, run_id,
                status="completed",
                finished_at=datetime.utcnow().isoformat(),
                duration_seconds=round(duration, 2),
            )
            return

        # Step 5: Generate newsletter
        logger.info("=== Step 5: Generating newsletter ===")
        newsletter = generate_newsletter(
            top_articles,
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            db_path=db_path,
        )

        # Save HTML preview
        preview_path = Path("newsletter_preview.html")
        preview_path.write_text(newsletter.html_content, encoding="utf-8")
        logger.info(f"Newsletter preview saved to {preview_path.resolve()}")

        update_pipeline_run(db_path, run_id, articles_sent=len(top_articles))

        subject = newsletter.subject_line or "Knowledge in Chain"

        # Step 5b: Generate LinkedIn post
        logger.info("=== Step 5b: Generating LinkedIn post ===")
        linkedin_post = generate_linkedin_post(
            top_articles,
            api_key=settings.anthropic_api_key,
            model=settings.claude_model,
            base_url=settings.base_url,
            db_path=db_path,
            run_id=run_id,
        )
        if linkedin_post:
            logger.info(f"LinkedIn post:\n{linkedin_post}")

        # Step 6: Send / save
        if mode == "preview":
            # Save as pending newsletter
            nl_id = save_pending_newsletter(
                db_path, run_id, subject, newsletter.html_content,
                json_data=newsletter.json_data,
            )
            if linkedin_post:
                save_linkedin_post(db_path, nl_id, linkedin_post)
            logger.info(f"Newsletter saved as pending (id={nl_id})")

            # Send preview only to review_email
            review_email = settings.review_email
            if not review_email:
                logger.warning("REVIEW_EMAIL not set, skipping preview send")
            else:
                logger.info(f"Sending preview to {review_email}")
                preview_subject = f"[PREVIEW] {subject}"
                email_result = send_newsletter(
                    html_content=newsletter.html_content,
                    from_email=settings.newsletter_from_email,
                    subscribers=[review_email],
                    api_key=settings.resend_api_key,
                    base_url=settings.base_url,
                    db_path=db_path,
                    pipeline_run_id=run_id,
                    subject=preview_subject,
                )
                logger.info(f"Preview sent: {email_result['sent']} ok, {email_result['failed']} failed")
        elif dry_run:
            logger.info("=== Dry run: skipping email send ===")
            # Save to archive even in dry-run
            nl_id = save_pending_newsletter(
                db_path, run_id, subject, newsletter.html_content,
                json_data=newsletter.json_data,
            )
            if linkedin_post:
                save_linkedin_post(db_path, nl_id, linkedin_post)
            mark_newsletter_sent(db_path, nl_id)
            logger.info(f"Newsletter archived (id={nl_id})")
        else:
            # Full mode: send to all subscribers
            logger.info("=== Step 6: Sending newsletter ===")
            env_subscribers = set(settings.subscriber_list)
            db_subscribers = set(get_active_subscribers(db_path))
            all_subscribers = sorted(env_subscribers | db_subscribers)
            logger.info(f"Sending to {len(all_subscribers)} subscribers ({len(env_subscribers)} env, {len(db_subscribers)} db)")

            email_result = send_newsletter(
                html_content=newsletter.html_content,
                from_email=settings.newsletter_from_email,
                subscribers=all_subscribers,
                api_key=settings.resend_api_key,
                base_url=settings.base_url,
                db_path=db_path,
                pipeline_run_id=run_id,
                subject=subject,
            )
            update_pipeline_run(
                db_path, run_id,
                emails_sent=email_result["sent"],
                emails_failed=email_result["failed"],
            )
            if email_result["sent"] > 0:
                mark_as_sent(db_path, [a.url for a in top_articles])
                # Save to archive
                nl_id = save_pending_newsletter(
                    db_path, run_id, subject, newsletter.html_content,
                    json_data=newsletter.json_data,
                )
                if linkedin_post:
                    save_linkedin_post(db_path, nl_id, linkedin_post)
                mark_newsletter_sent(db_path, nl_id)
                logger.info(f"Newsletter sent and archived (id={nl_id}): {email_result['sent']} ok, {email_result['failed']} failed")
            else:
                logger.error("Newsletter sending failed")

        duration = time.time() - start_time
        update_pipeline_run(
            db_path, run_id,
            status="completed",
            finished_at=datetime.utcnow().isoformat(),
            duration_seconds=round(duration, 2),
        )
        logger.info(f"Pipeline run {run_id} completed in {duration:.1f}s")

    except Exception as exc:
        duration = time.time() - start_time
        update_pipeline_run(
            db_path, run_id,
            status="failed",
            finished_at=datetime.utcnow().isoformat(),
            duration_seconds=round(duration, 2),
            error_message=str(exc),
        )
        logger.exception(f"Pipeline run {run_id} failed after {duration:.1f}s")
        raise


# Global reference so health check can verify the thread is alive
_scheduler_thread: threading.Thread | None = None


def start_scheduler_thread() -> threading.Thread:
    """Launch the scheduler in a daemon thread. Returns the thread."""
    global _scheduler_thread
    t = threading.Thread(target=run_scheduler, daemon=True, name="scheduler")
    t.start()
    _scheduler_thread = t
    return t


def _schedule_job(day: str, time_str: str, func, label: str) -> None:
    """Register a single weekly job."""
    scheduler_map = {
        "monday": schedule.every().monday,
        "tuesday": schedule.every().tuesday,
        "wednesday": schedule.every().wednesday,
        "thursday": schedule.every().thursday,
        "friday": schedule.every().friday,
        "saturday": schedule.every().saturday,
        "sunday": schedule.every().sunday,
    }
    job = scheduler_map.get(day.lower())
    if job is None:
        logger.error(f"Invalid schedule day for {label}: {day}")
        sys.exit(1)
    job.at(time_str).do(func)
    logger.info(f"Scheduled {label}: every {day} at {time_str}")


def run_scheduler() -> None:
    """Run dual schedule: preview on Saturday, send-pending on Monday."""
    _schedule_job(
        settings.preview_schedule_day,
        settings.preview_schedule_time,
        lambda: run_pipeline(mode="preview"),
        "preview",
    )
    _schedule_job(
        settings.send_schedule_day,
        settings.send_schedule_time,
        lambda: run_pipeline(mode="send-pending"),
        "send-pending",
    )

    while True:
        try:
            schedule.run_pending()
        except Exception:
            logger.exception("Scheduler: error running pending jobs")
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
        "--preview",
        action="store_true",
        help="Generate newsletter, save as pending, send preview to review email only",
    )
    parser.add_argument(
        "--send-pending",
        action="store_true",
        help="Send the most recent pending newsletter to all subscribers",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a weekly schedule (preview Saturday, send Monday)",
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
    elif args.preview:
        run_pipeline(mode="preview")
    elif args.send_pending:
        run_pipeline(mode="send-pending")
    else:
        run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    cli()
