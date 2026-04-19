# senior_generator.py
# Nostalgia Hook → High-Value Funnel 콘텐츠 생성
# 기존 EngineLoader(Gemini+Claude 폴백) 재사용

import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'bots'))

from engine_loader import EngineLoader
from senior_config import (
    get_category_for_today,
    get_keywords_for_category,
    get_random_nostalgia_hook,
    get_bridge_for_category,
    CATEGORIES,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────

def build_system_prompt() -> str:
    return """You are a blog writer for "Today's Senior TV," a lifestyle and information blog FOR American Baby Boomers and Gen X seniors (ages 60–78).

PERSONA:
- Write like a warm, knowledgeable friend who is also a senior — someone who remembers the good old days AND understands today's challenges.
- Tone: conversational, trustworthy, slightly nostalgic, occasionally humorous. Never preachy. Never condescending.

STRICT LANGUAGE RULES:
- Natural American English. No British spellings.
- NEVER use: "crucial," "delve," "moreover," "leverage," "utilize," "it's important to note," "in conclusion," "furthermore," "navigate," "embark," "seamlessly," "game-changer."
- Use contractions naturally (it's, you'll, we've, don't).
- Short sentences. Plain words. Like talking to a neighbor over the fence.

CONTENT RULES:
- 4-part funnel structure: Hook → Bridge → Main Info → CTA
- Include target keywords naturally in H1 and H2 headings.
- Genuinely useful info — not fluff. Seniors can tell the difference.
- Do not make up statistics. Use general framing ("according to AARP," "Medicare data shows").
- Include at least one relatable personal example in the Main section.
- CTA must feel helpful, not pushy.

OUTPUT FORMAT:
Return ONLY a valid JSON object. No markdown fences. No explanation. No extra text before or after.

Schema:
{
  "title": "SEO H1 title — include primary keyword, under 65 characters",
  "meta_description": "Under 155 characters. Human-written. Contains primary keyword.",
  "html_content": "Full post as HTML. Use <h2>,<p>,<ul>,<li>,<strong>,<em>. No <html><head><body> tags.",
  "tags": ["tag1","tag2","tag3","tag4","tag5"],
  "image_query": "Unsplash search query for nostalgic hero image"
}"""


def build_user_prompt(category_key, category_info, primary_keyword,
                      supporting_keywords, nostalgia_hook, bridge_sentence) -> str:
    sup_kw = '\n'.join(f'  - {kw}' for kw in supporting_keywords)
    return f"""Write a blog post for "Today's Senior TV."

CATEGORY: {category_info['name']}
PRIMARY KEYWORD (use in H1 and at least one H2): "{primary_keyword}"
SUPPORTING KEYWORDS (weave naturally):
{sup_kw}

4-PART STRUCTURE:

PART 1 — HOOK (Nostalgia, ~20%):
Era: {nostalgia_hook['era']} | Topic: {nostalgia_hook['topic']}
Opening to adapt: "{nostalgia_hook['hook']}"
Make the reader feel transported. Sensory details (sounds, smells, sights).
Use <h2> for this section.

PART 2 — BRIDGE (~10%):
Shift from nostalgia to today's topic naturally using this as inspiration:
"{bridge_sentence}"
Keep it short — 1-2 paragraphs.

PART 3 — MAIN VALUE ({category_info['name']}, ~60%):
- Include primary keyword "{primary_keyword}" in an <h2> heading.
- Practical, useful info broken into digestible chunks.
- At least one real-life example or scenario.
- Naturally weave in supporting keywords.
- 400–550 words in this section.

PART 4 — CTA (~10%):
- Low-pressure call to action guiding the reader to next step.
- Frame it as doing something kind for themselves or family.
- End with one warm encouraging sentence.

SEO: H1 must contain primary keyword (under 65 chars). At least 2 H2s with keywords. Total 700–900 words.

Return ONLY the JSON object. No preamble. No markdown fences."""


# ─────────────────────────────────────────
# JSON 파싱
# ─────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    clean = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    clean = re.sub(r'\s*```$', '', clean).strip()
    # JSON 블록만 추출
    start = clean.find('{')
    end = clean.rfind('}')
    if start != -1 and end != -1:
        clean = clean[start:end+1]
    return json.loads(clean)


# ─────────────────────────────────────────
# MAIN GENERATE FUNCTION
# ─────────────────────────────────────────

def generate_post(category_key: str = None) -> dict:
    if category_key is None:
        category_key, category_info = get_category_for_today()
    else:
        category_info = CATEGORIES[category_key]

    keywords = get_keywords_for_category(category_key, n=4)
    primary_keyword = keywords[0]
    supporting_keywords = keywords[1:]
    nostalgia_hook = get_random_nostalgia_hook()
    bridge_sentence = get_bridge_for_category(category_key)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        category_key, category_info, primary_keyword,
        supporting_keywords, nostalgia_hook, bridge_sentence,
    )

    logger.info(f'카테고리: {category_key} / {category_info["name"]}')
    logger.info(f'Primary Keyword: {primary_keyword}')
    logger.info(f'Nostalgia Hook: {nostalgia_hook["topic"]} ({nostalgia_hook["era"]})')

    # 기존 EngineLoader 사용 (Gemini → Claude 자동 폴백)
    writer = EngineLoader().get_writer()
    raw = writer.write(user_prompt, system=system_prompt)

    if not raw:
        raise RuntimeError('콘텐츠 생성 실패: 빈 응답')

    post_data = _parse_json(raw)
    post_data['category_key'] = category_key
    post_data['category_info'] = category_info
    post_data['primary_keyword'] = primary_keyword

    return post_data
