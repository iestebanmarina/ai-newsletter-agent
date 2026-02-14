import logging
from datetime import datetime
from urllib.parse import quote

import resend

from .db import log_email_send

logger = logging.getLogger(__name__)


def send_newsletter(
    html_content: str,
    from_email: str,
    subscribers: list[str],
    api_key: str,
    base_url: str = "",
    db_path: str = "",
    pipeline_run_id: str = "",
    subject: str = "",
) -> dict:
    """Send the newsletter HTML to all subscribers via Resend.

    Each subscriber gets a personalized copy with their own unsubscribe link.
    The html_content should contain {{UNSUBSCRIBE_URL}} as a placeholder.

    Returns dict with "sent" and "failed" counts.
    """
    result = {"sent": 0, "failed": 0}

    if not subscribers:
        logger.warning("No subscribers configured, skipping email send")
        return result

    if not api_key:
        logger.warning("Resend API key not configured, skipping email send")
        return result

    resend.api_key = api_key
    if not subject:
        today = datetime.utcnow().strftime("%B %d, %Y")
        subject = f"Knowledge in Chain - {today}"
    base_url = base_url.rstrip("/")

    for email in subscribers:
        try:
            unsubscribe_url = f"{base_url}/api/unsubscribe?email={quote(email)}"
            personalized_html = html_content.replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)
            resend.Emails.send({
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": personalized_html,
            })
            logger.info(f"Newsletter sent to {email}")
            result["sent"] += 1
            if db_path:
                try:
                    log_email_send(
                        db_path,
                        pipeline_run_id=pipeline_run_id,
                        recipient=email,
                        status="sent",
                    )
                except Exception:
                    logger.debug("Failed to log email send", exc_info=True)
        except Exception as exc:
            logger.exception(f"Failed to send newsletter to {email}")
            result["failed"] += 1
            if db_path:
                try:
                    log_email_send(
                        db_path,
                        pipeline_run_id=pipeline_run_id,
                        recipient=email,
                        status="failed",
                        error_message=str(exc),
                    )
                except Exception:
                    logger.debug("Failed to log email failure", exc_info=True)

    return result
