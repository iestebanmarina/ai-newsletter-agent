import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI-Newsletter-Agent/0.1; +https://github.com)",
    "Accept": "text/html,application/xhtml+xml",
}


def scrape_article_content(url: str, timeout: float = 15.0) -> str:
    """Scrape the main text content from an article URL.

    Returns the extracted text, or empty string on failure.
    """
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=HEADERS
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception:
        logger.debug(f"Failed to fetch: {url}")
        return ""

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return ""

    try:
        return _extract_text(response.text)
    except Exception:
        logger.debug(f"Failed to parse: {url}")
        return ""


def _extract_text(html: str) -> str:
    """Extract main article text from HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content elements
    for tag in soup.find_all(
        ["script", "style", "nav", "header", "footer", "aside", "form", "iframe"]
    ):
        tag.decompose()

    # Try to find the main article content
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find(class_=re.compile(r"article|post|content|entry", re.I))
    )

    target = article if article else soup.body
    if target is None:
        return ""

    # Extract text from paragraphs
    paragraphs = target.find_all("p")
    text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    # Truncate to a reasonable length for Claude processing
    if len(text) > 5000:
        text = text[:5000] + "..."

    return text
