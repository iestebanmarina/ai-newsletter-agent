import logging
from datetime import datetime
from urllib.parse import quote

import resend

logger = logging.getLogger(__name__)


def send_newsletter(
    html_content: str,
    from_email: str,
    subscribers: list[str],
    api_key: str,
    base_url: str = "",
) -> bool:
    """Send the newsletter HTML to all subscribers via Resend.

    Each subscriber gets a personalized copy with their own unsubscribe link.
    The html_content should contain {{UNSUBSCRIBE_URL}} as a placeholder.
    """
    if not subscribers:
        logger.warning("No subscribers configured, skipping email send")
        return False

    if not api_key:
        logger.warning("Resend API key not configured, skipping email send")
        return False

    resend.api_key = api_key
    today = datetime.utcnow().strftime("%B %d, %Y")
    subject = f"AI Weekly Digest - {today}"
    base_url = base_url.rstrip("/")

    success = True
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
        except Exception:
            logger.exception(f"Failed to send newsletter to {email}")
            success = False

    return success
