import logging

import anthropic

from .config import settings
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

LINKEDIN_SYSTEM_PROMPT_ES = """\
Escribes posts para LinkedIn que promocionan la newsletter semanal de IA "Knowledge in Chain".

Reglas:
- Máx. ~1300 caracteres / ~200 palabras
- Empieza con un gancho que capture la atención desde la primera línea. Sin "Esta semana en...".
- Lista 3-5 puntos clave de la newsletter de esta semana con frases cortas
- Cierra con una llamada a la acción para suscribirse (incluye la URL proporcionada)
- Voz de Iñigo: frases cortas, tono invitacional, autoridad desde la experiencia concreta, no desde títulos
- Sin guiones largos (—). Usa punto, coma o punto y coma
- Usa emojis con moderación (máx. 1-2)
- Hashtags al final (exactamente estos 4): #EstrategiaIA #TransformacionIA #BuildInPublic #Innovacion
- Rota entre estas tres CTAs (elige la que mejor encaje con el contenido de la semana):
  · "¿Te unes? Suscríbete en: [URL]"
  · "La newsletter que traduce la IA a decisiones reales: [URL]"
  · "Cada semana, lo que importa de la IA explicado para quienes toman decisiones: [URL]"
- Output SOLO el texto del post, nada más
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
    active_prompt = LINKEDIN_SYSTEM_PROMPT_ES if settings.newsletter_style == "spanish" else LINKEDIN_SYSTEM_PROMPT

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=active_prompt,
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
