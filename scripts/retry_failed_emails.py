#!/usr/bin/env python3
"""Script to retry sending failed emails from today."""
import sqlite3
from datetime import datetime, date
from pathlib import Path

from src.newsletter.emailer import send_newsletter
from src.newsletter.config import Settings

def get_failed_emails_today(db_path: str) -> list[str]:
    """Get list of email addresses that failed today."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    today = date.today().isoformat()

    cursor = conn.execute(
        """SELECT DISTINCT recipient
           FROM email_log
           WHERE status = 'failed'
           AND DATE(created_at) = ?
           ORDER BY recipient""",
        (today,)
    )

    failed_emails = [row["recipient"] for row in cursor.fetchall()]
    conn.close()

    return failed_emails


def get_latest_newsletter(db_path: str) -> tuple[str, str] | None:
    """Get the HTML content and subject of the most recent newsletter."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """SELECT html_content, edition_number, edition_date
           FROM pending_newsletters
           WHERE status = 'sent'
           ORDER BY id DESC
           LIMIT 1"""
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    # Construct subject line
    subject = f"Knowledge in Chain - Edition #{row['edition_number']}"

    return row["html_content"], subject


def main():
    settings = Settings()
    db_path = settings.database_path

    print(f"Database path: {db_path}")
    print(f"Checking for failed emails on {date.today().isoformat()}...\n")

    # Get failed emails
    failed_emails = get_failed_emails_today(db_path)

    if not failed_emails:
        print("✓ No failed emails found today!")
        return

    print(f"Found {len(failed_emails)} failed email(s):")
    for email in failed_emails:
        print(f"  - {email}")

    # Get newsletter content
    newsletter_data = get_latest_newsletter(db_path)

    if not newsletter_data:
        print("\n✗ Error: Could not find the newsletter content to resend")
        return

    html_content, subject = newsletter_data
    print(f"\nNewsletter subject: {subject}")

    # Ask for confirmation
    response = input(f"\nRetry sending to these {len(failed_emails)} recipient(s)? (yes/no): ")

    if response.lower() not in ("yes", "y"):
        print("Cancelled.")
        return

    print(f"\nResending with rate limiting (0.6s delay between emails)...")

    # Resend
    result = send_newsletter(
        html_content=html_content,
        from_email=settings.newsletter_from_email,
        subscribers=failed_emails,
        api_key=settings.resend_api_key,
        base_url=settings.base_url,
        db_path=db_path,
        pipeline_run_id="manual_retry",
        subject=subject,
    )

    print(f"\n✓ Resend complete!")
    print(f"  Sent: {result['sent']}")
    print(f"  Failed: {result['failed']}")


if __name__ == "__main__":
    main()
