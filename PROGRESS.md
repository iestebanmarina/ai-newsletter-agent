# Knowledge in Chain — Progress Tracker

Track of product changes, improvements, and experiments. Updated each working session.

---

## 2026-03-03 — Phase 1: Differentiation (Content & Positioning)

### Context
Competitive analysis identified the core gap: the newsletter already has a unique practice-layer (Prompt Lab, Workflow Shift, Challenge) but presents itself like a news digest. Phase 1 aligns the product's exterior with its interior.

### Changes

#### 1. New section: Tool of the Week (section 7)
**Files:** `src/newsletter/generator.py`, `src/newsletter/templates/newsletter.html`
- Added section 7 (`tool_of_week`) to both EN and ES system prompts
- JSON schema: `name`, `what_it_does`, `best_for`, `how_to_start`, `free_plan` (bool), `url`
- Template: rendered after Weekly Challenge with free/paid badge, action-oriented layout
- Rule: Claude must never recommend the same tool twice across editions
- Rationale: "Tool of the Week" is the highest-engagement content type in AI newsletters. Increases opens and natural referrals.

#### 2. New field: Learning Summary (3-bullet edition preview)
**Files:** `src/newsletter/generator.py`, `src/newsletter/templates/newsletter.html`
- Added section 8 (`learning_summary`) to both EN and ES system prompts
- JSON schema: array of 3 strings, each completing "This week: [X]"
- Template: appears at top of email (after header, before editor note) as a "// This week" block
- Rationale: Readers know exactly what value to expect before reading. Reduces "why did I open this?" and increases read-through.

#### 3. Landing page repositioning
**File:** `src/newsletter/templates/landing.html`
- Title: "Knowledge in Chain - The Weekly AI Practice"
- Headline: "The weekly AI practice that makes you better. Not just informed."
- Value hook: "Most AI newsletters tell you what happened. This one teaches you what to do."
- Value lines: expanded to 6 items, including Tool of the Week
- Closer: "7-10 min read. Inform, translate, practice. Every week."
- Feature cards: repositioned around learning system vs. news digest
- Rationale: 30%+ of sign-ups come through the landing page. If the promise doesn't match the content, churn is high.

#### 4. System prompt fix
**File:** `src/newsletter/generator.py`
- Fixed incorrect section numbering: "### 3. // USE THIS" corrected to "### 4. // USE THIS"

---

## Upcoming — Phase 2

- [ ] Weekly question ("Pregunta de la semana") — community engagement hook
- [ ] Workflow Shift categories (Communication / Analysis / Research / Management / Creativity) — prevents repetition, enables archive navigation
- [ ] SEO meta tags on newsletter archive pages

## Upcoming — Phase 3 (Strategic)

- [ ] Spanish version as differentiated product (Cadena de Conocimiento)
- [ ] Welcome email sequence (3 emails: what this is, how to get value, best past edition)
- [ ] Referral program (Sparkloop or custom)
