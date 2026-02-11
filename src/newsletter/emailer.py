import logging
from datetime import datetime

import resend

logger = logging.getLogger(__name__)


def send_newsletter(
    html_content: str,
    from_email: str,
    subscribers: list[str],
    api_key: str,
) -> bool:
    """Send the newsletter HTML to all subscribers via Resend."""
    if not subscribers:
        logger.warning("No subscribers configured, skipping email send")
        return False

    if not api_key:
        logger.warning("Resend API key not configured, skipping email send")
        return False

    resend.api_key = api_key
    today = datetime.utcnow().strftime("%B %d, %Y")
    subject = f"AI Weekly Digest - {today}"

    success = True
    for email in subscribers:
        try:
            resend.Emails.send({
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_content,
            })
            logger.info(f"Newsletter sent to {email}")
        except Exception:
            logger.exception(f"Failed to send newsletter to {email}")
            success = False

    return success
