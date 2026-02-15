import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic
from jinja2 import Environment, FileSystemLoader

from .db import (
    build_history_context,
    get_history,
    log_api_usage,
    save_to_history,
)
from .models import Newsletter

logger = logging.getLogger(__name__)

# Module-level pipeline context (set by main.py before calling generate_newsletter)
_current_db_path: str = ""
_current_run_id: str = ""


def set_pipeline_context(db_path: str, run_id: str) -> None:
    global _current_db_path, _current_run_id
    _current_db_path = db_path
    _current_run_id = run_id


SYSTEM_PROMPT = """You are the editor of "Knowledge in Chain", a weekly AI newsletter for NON-EXPERT readers.
Your readers are smart professionals (managers, entrepreneurs, creatives, students) who are NOT engineers or data scientists. They want to UNDERSTAND AI and USE it practically, not read about benchmarks and model architectures.

You will receive this week's top AI articles (title, source, summary, relevance score). From these, generate a newsletter with EXACTLY 6 sections. Write in English.

## SECTIONS

### 1. // SIGNAL — The one story that matters
Pick THE single most impactful story of the week. Explain it as if talking to a smart friend who doesn't follow AI news.
Format:
- **Headline**: A rewritten, human-friendly headline (not the original article title)
- **What happened**: 2-3 sentences, plain language, no jargon
- **Why it matters**: 2-3 sentences explaining the real-world impact
- **What changes for you**: 1-2 sentences with a concrete takeaway the reader can act on
- **source_url**: The URL of the article you chose

### 2. // RADAR — 10 stories worth knowing
Select the 10 most relevant stories from the remaining articles (NOT the one used in SIGNAL). For each story, structure it as:
- **takeaway**: One sentence. What this means for the reader. Start with a verb or implication, not a description of the news. This is the FIRST thing the reader sees — make it practical and direct.
- **context**: 2-3 sentences. The background: why this is happening, what forces are at play, what trend it connects to.
- **summary**: 1-2 sentences. Brief factual description of the actual news/event.
- **source**: The article source name (e.g., "MIT Technology Review")
- **url**: The article URL

IMPORTANT for takeaway: Do NOT write "Company X did Y". Write what it MEANS: "You can now...", "This could change how...", "If you use X, expect...", "The cost of X just dropped because...". Always reader-first.

### 3. // TRANSLATE — Tech concept decoded (pick one concept from the week's news)
Pick ONE technical concept that appeared in this week's news (e.g., "context window", "RAG", "fine-tuning", "agents", "reasoning models", "open source AI", "multimodal"). Explain it using an everyday analogy.
Format:
- **Concept**: The technical term
- **Analogy**: "X is like [everyday analogy]..."
- **In practice**: What this means the reader can actually do
- **Why now**: Why this concept is relevant this week (tie to news)

### 3. // USE THIS — Prompt of the week
Create a practical, copy-paste prompt for ChatGPT or Claude that solves a REAL everyday problem. The prompt should be related to this week's theme.
Format:
- **Problem**: The real-world problem this solves (1 sentence)
- **The prompt**: The exact prompt to copy-paste (in a code block). Make it a GREAT prompt that demonstrates good prompting technique.
- **Example output**: A brief example of what the AI would return (3-5 lines)
- **Why it works**: 1-2 sentences explaining the prompting technique used (teaches the reader to build their own prompts)
- **Difficulty**: beginner / intermediate / advanced

### 5. // BEFORE → AFTER — Workflow transformation
Show a specific common task done the traditional way vs. with AI assistance. Be CONCRETE and specific.
Format:
- **Task**: What the task is (e.g., "Preparing a competitive analysis")
- **Before**: How people typically do it (steps, time estimate)
- **After**: How to do it with AI (steps with actual approach, time estimate)
- **The key insight**: What makes the AI approach fundamentally different (not just faster)

### 6. // CHALLENGE — Your weekly exercise
Design a hands-on exercise the reader can do RIGHT NOW with any LLM (ChatGPT, Claude, Gemini). It should:
- Use something the reader ALREADY has (an email, a document, a problem they're facing)
- Teach a transferable skill
- Have a clear "aha moment"

The challenge has ONE theme but THREE levels so every reader finds their entry point:
Format:
- **theme**: The core skill or topic this challenge teaches (1 sentence)
- **level_1_title**: Short label for level 1 (e.g., "First steps")
- **level_1**: Beginner version — a simple, concrete exercise anyone can do in 5 minutes. No prior AI experience needed. Give clear step-by-step instructions.
- **level_2_title**: Short label for level 2 (e.g., "Push further")
- **level_2**: Intermediate version — builds on level 1 by adding a technique (iteration, role-play, structured output). 5-10 minutes.
- **level_3_title**: Short label for level 3 (e.g., "Go deep")
- **level_3**: Advanced version — combines multiple skills, requires more critical thinking, produces a reusable workflow. 10-15 minutes.
- **what_youll_learn**: The transferable skill this builds (applies to ALL levels)

## UNIQUENESS & PROGRESSION RULES (CRITICAL)
You will also receive a HISTORY of all previous editions. You MUST:
- **NEVER repeat** a TRANSLATE concept that was already covered. Pick a NEW concept each week.
- **NEVER repeat** a USE THIS prompt that solves the same problem. Each week must teach a different skill.
- **NEVER repeat** a BEFORE→AFTER task. Find a new workflow to transform.
- **NEVER reuse** a SIGNAL article URL that appeared as signal in a previous edition.
- For RADAR: avoid URLs already covered in previous editions when possible.
- If a concept was covered before but there's a SIGNIFICANT new development that justifies revisiting it, you MAY reference it briefly while focusing on what's NEW. Explicitly note: "We covered [concept] in edition N — here's what changed."

### Challenge progression
Each challenge has 3 levels built in, so ALL readers participate every week regardless of experience.
But the THEME of each challenge should follow a progressive curriculum across editions:
- Early editions: Themes around basic AI interaction (summarizing, drafting, brainstorming, Q&A)
- Mid editions: Themes around structured techniques (analysis, comparison, role-play, iteration)
- Later editions: Themes around workflows (multi-step, chaining outputs, building systems, teaching others)

Each challenge should introduce a DIFFERENT theme from all previous editions. Never repeat the same core skill.
When relevant, reference past challenges: "If you did edition N's challenge, you already know how to [X] — this week builds on that."

## GENERAL RULES
- NO jargon without explanation. If you must use a technical term, explain it in parentheses.
- Write in a warm, direct tone. Like a knowledgeable friend, not a professor.
- Every section must be ACTIONABLE. The reader should be able to DO something after reading.
- The 6 sections should feel thematically connected when possible (same week's theme threads through).
- Keep it concise. The entire newsletter should take 7-10 minutes to read.
- DO NOT mention specific model version numbers or pricing unless directly relevant.
- Each edition must feel FRESH. A returning reader should never think "I've seen this before".
- NEVER use em-dashes (—). Use periods, commas, or semicolons instead. Restructure sentences if needed. Em-dashes feel robotic and formulaic. Write like a human: short sentences, natural punctuation.

Return your response as a JSON object with this exact structure:
{
  "subject_line": "A compelling email subject line (max 60 chars)",
  "signal": {
    "headline": "...",
    "what_happened": "...",
    "why_it_matters": "...",
    "what_changes": "...",
    "source_url": "..."
  },
  "radar": [
    {
      "takeaway": "...",
      "context": "...",
      "summary": "...",
      "source": "...",
      "url": "..."
    }
  ],
  "translate": {
    "concept": "...",
    "analogy": "...",
    "in_practice": "...",
    "why_now": "..."
  },
  "use_this": {
    "problem": "...",
    "prompt": "...",
    "example_output": "...",
    "why_it_works": "...",
    "difficulty": "beginner|intermediate|advanced"
  },
  "before_after": {
    "task": "...",
    "before": "...",
    "after": "...",
    "key_insight": "..."
  },
  "challenge": {
    "theme": "...",
    "level_1_title": "...",
    "level_1": "...",
    "level_2_title": "...",
    "level_2": "...",
    "level_3_title": "...",
    "level_3": "...",
    "what_youll_learn": "..."
  }
}"""

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_newsletter(
    articles: list,
    api_key: str,
    model: str,
    db_path: str = "",
    save_history: bool = True,
    edition_date: str = "",
) -> Newsletter:
    """Generate a complete newsletter using the 6-section Knowledge in Chain format.

    Args:
        save_history: If False, don't save to history (for preview mode).
        edition_date: Date string for the newsletter header (e.g. "February 17, 2026").
                      Defaults to UTC today if empty.
    """
    effective_db_path = db_path or _current_db_path

    # Load history context
    if effective_db_path:
        history = get_history(effective_db_path)
    else:
        history = []

    week_number = len(history) + 1
    history_context = build_history_context(history)

    if not edition_date:
        edition_date = datetime.utcnow().strftime("%B %d, %Y")

    logger.info(f"Edition #{week_number} ({len(history)} previous editions in history)")

    # Prepare article data for the prompt
    articles_for_prompt = _prepare_articles(articles)

    # Call Claude to generate the newsletter content
    client = anthropic.Anthropic(api_key=api_key)
    data = _generate_content(client, model, articles_for_prompt, history_context, week_number, edition_date)

    # Render HTML via Jinja2 template
    html = render_html(data, week_number, edition_date)

    # Save to history for cross-edition memory (skip in preview/dry-run)
    if save_history and effective_db_path:
        save_to_history(effective_db_path, data, week_number)
        logger.info(f"Saved edition #{week_number} to history")

    json_data = json.dumps(data, ensure_ascii=False)

    newsletter = Newsletter(
        date=datetime.utcnow(),
        subject_line=data.get("subject_line", "Knowledge in Chain"),
        html_content=html,
        json_data=json_data,
    )

    logger.info(f"Generated newsletter edition #{week_number} with subject: {newsletter.subject_line}")
    return newsletter


def _prepare_articles(articles: list) -> list[dict]:
    """Convert Article objects (or dicts) into dicts suitable for the prompt."""
    result = []
    for a in articles:
        if isinstance(a, dict):
            result.append(a)
        else:
            result.append({
                "title": a.title,
                "source": a.source,
                "category": a.category if hasattr(a, "category") else "",
                "relevance_score": a.relevance_score if hasattr(a, "relevance_score") else 0,
                "summary": a.summary if hasattr(a, "summary") else "",
                "url": a.url,
            })
    return result


def _generate_content(
    client: anthropic.Anthropic,
    model: str,
    articles: list[dict],
    history_context: str,
    week_number: int,
    edition_date: str = "",
) -> dict:
    """Call Claude to generate the full newsletter JSON."""
    articles_text = json.dumps(articles, indent=2)

    if not edition_date:
        edition_date = datetime.utcnow().strftime("%B %d, %Y")

    user_message_parts = [
        f"Today's date: {edition_date}",
        f"This is EDITION #{week_number} of the newsletter.",
        "",
        "=== HISTORY OF PREVIOUS EDITIONS ===",
        history_context,
        "",
        "=== THIS WEEK'S CURATED ARTICLES ===",
        articles_text,
        "",
        "Generate the newsletter following the exact JSON structure specified. Remember: NO repetition of past concepts, prompts, or tasks. Build on previous challenges progressively.",
    ]

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": "\n".join(user_message_parts),
            }],
        )

        # Log API usage
        if _current_db_path:
            try:
                log_api_usage(
                    _current_db_path,
                    pipeline_run_id=_current_run_id,
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    step="newsletter_generation",
                )
            except Exception:
                logger.debug("Failed to log API usage", exc_info=True)

        logger.info(
            f"Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out"
        )

        text = response.content[0].text.strip()

        # Parse JSON (handle code fences)
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        return json.loads(text)

    except json.JSONDecodeError:
        logger.exception("Failed to parse Claude response as JSON")
        raise
    except Exception:
        logger.exception("Failed to generate newsletter content")
        raise


def render_html(data: dict, week_number: int, edition_date: str = "") -> str:
    """Render the newsletter HTML using the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )
    template = env.get_template("newsletter.html")

    if not edition_date:
        edition_date = datetime.utcnow().strftime("%B %d, %Y")
    today = edition_date

    # Compute short source URL for the signal section
    source_url = data.get("signal", {}).get("source_url", "")
    source_short = source_url.replace("https://", "").replace("http://", "")
    if len(source_short) > 50:
        source_short = source_short[:50] + "..."

    return template.render(
        subject_line=data.get("subject_line", "Knowledge in Chain"),
        edition_number=week_number,
        date=today,
        signal=data.get("signal", {}),
        signal_source_short=source_short,
        radar=data.get("radar", []),
        translate=data.get("translate", {}),
        use_this=data.get("use_this", {}),
        before_after=data.get("before_after", {}),
        challenge=data.get("challenge", {}),
    )
