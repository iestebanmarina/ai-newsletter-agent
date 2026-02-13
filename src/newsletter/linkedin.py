import logging

import anthropic

from .db import log_api_usage
from .models import Article

logger = logging.getLogger(__name__)

LINKEDIN_SYSTEM_PROMPT = """\
You write engaging LinkedIn posts promoting a weekly AI newsletter called "Knowledge in Chain".

Rules:
- Max ~1300 characters / ~200 words
- Start with a hook that grabs attention
- List 3-5 key takeaways from this week's newsletter
- End with a CTA to subscribe (include the URL provided)
- Professional but approachable tone, suitable for LinkedIn
- Use line breaks for readability
- Use emojis sparingly (1-2 max)
- Do NOT use hashtags excessively (2-3 max at the end)
- Output ONLY the post text, nothing else
"""


def generate_linkedin_post(
    articles: list[Article],
    api_key: str,
    model: str,
    base_url: str = "",
    db_path: str = "",
    run_id: str = "",
) -> str:
    """Generate a LinkedIn post summarizing the newsletter's top articles."""
    summaries = []
    for a in articles[:10]:
        summaries.append(f"- [{a.source}] {a.title}: {a.summary}")
    articles_text = "\n".join(summaries)

    subscribe_url = base_url.rstrip("/") if base_url else "https://knowledgeinchain.com"

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=LINKEDIN_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Subscribe URL: {subscribe_url}\n\n"
                        f"This week's top articles:\n{articles_text}\n\n"
                        "Write the LinkedIn post."
                    ),
                }
            ],
        )

        if db_path:
            try:
                log_api_usage(
                    db_path,
                    pipeline_run_id=run_id,
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    step="linkedin_post",
                )
            except Exception:
                logger.debug("Failed to log API usage", exc_info=True)

        post_text = response.content[0].text.strip()
        logger.info(f"LinkedIn post generated ({len(post_text)} chars)")
        return post_text

    except Exception:
        logger.exception("Failed to generate LinkedIn post")
        return ""
