# senior_generator.py
# Expert Persona Hook → High-Value Funnel 콘텐츠 생성 (v2.0)
# 기존 EngineLoader(Gemini+Claude 폴백) 재사용

import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'bots'))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

from engine_loader import EngineLoader
from senior_config import (
    get_category_for_today,
    get_keywords_for_category,
    get_hook_for_category,
    CATEGORIES,
)
from senior_collector import get_used_hook_angles

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# TAVILY 웹 리서치
# ─────────────────────────────────────────

def fetch_research(keyword: str, max_results: int = 5) -> str:
    """Tavily API로 키워드 관련 최신 웹 정보 수집 — 실패 시 빈 문자열 반환"""
    api_key = os.getenv('TAVILY_API_KEY', '')
    if not api_key:
        logger.warning('[RESEARCH] TAVILY_API_KEY 없음 — 리서치 스킵')
        return ''
    try:
        import requests as _req
        resp = _req.post(
            'https://api.tavily.com/search',
            json={
                'api_key': api_key,
                'query': keyword,
                'search_depth': 'advanced',
                'max_results': max_results,
                'include_answer': True,
                'include_raw_content': False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        lines = []
        # 요약 답변 (있을 경우)
        if data.get('answer'):
            lines.append(f'SUMMARY: {data["answer"]}')
        # 개별 결과 스니펫
        for r in data.get('results', []):
            title = r.get('title', '')
            content = r.get('content', '')[:300]
            url = r.get('url', '')
            if content:
                lines.append(f'- [{title}] {content} (source: {url})')

        research_text = '\n'.join(lines)
        logger.info(f'[RESEARCH] {len(data.get("results", []))}개 결과 수집 완료')
        return research_text

    except Exception as e:
        logger.warning(f'[RESEARCH] Tavily 실패: {e}')
        return ''


# ─────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────

def _load_annual_rates() -> dict:
    """data/annual_rates.json 로드 — 없으면 빈 dict 반환"""
    rates_path = Path(__file__).parent / 'data' / 'annual_rates.json'
    if rates_path.exists():
        try:
            return json.loads(rates_path.read_text(encoding='utf-8'))
        except Exception as e:
            logger.warning(f'[RATES] annual_rates.json 로드 실패: {e}')
    return {}


def _build_rates_block(rates: dict) -> str:
    """annual_rates.json → 프롬프트 주입용 텍스트 블록 생성"""
    if not rates:
        return ''
    year = rates.get('_meta', {}).get('year', rates.get('year', 'current year'))
    m = rates.get('medicare', {})
    ss = rates.get('social_security', {})
    ira = rates.get('ira_401k', {})
    rmd = rates.get('rmd', {})
    tax = rates.get('taxes', {})

    pb = m.get('part_b', {})
    pa = m.get('part_a', {})
    pd = m.get('part_d', {})
    ap = m.get('appeals', {})

    lines = [f'OFFICIAL {year} FIGURES — USE THESE EXACT NUMBERS, DO NOT SUBSTITUTE:']

    if pb:
        lines.append(f'  Medicare Part B deductible ({year}): ${pb.get("annual_deductible", "N/A")}')
        lines.append(f'  Medicare Part B standard premium ({year}): ${pb.get("standard_premium", "N/A")}/month')
    if pa:
        lines.append(f'  Medicare Part A inpatient deductible ({year}): ${pa.get("inpatient_hospital_deductible", "N/A")}')
        lines.append(f'  Skilled nursing days 21-100 coinsurance ({year}): ${pa.get("skilled_nursing_day_21_100_coinsurance", "N/A")}/day')
    if pd:
        lines.append(f'  Medicare Part D out-of-pocket cap ({year}): ${pd.get("oop_cap", "N/A")} (Inflation Reduction Act)')
        lines.append(f'  Part D max deductible ({year}): ${pd.get("max_deductible", "N/A")}')
        lines.append(f'  IMPORTANT: {pd.get("coverage_gap_status", "")}')
    if ap:
        lines.append(f'  Medicare ALJ hearing threshold ({year}): ${ap.get("alj_hearing_threshold", "N/A")}')
    if ss:
        lines.append(f'  Social Security COLA {year}: {ss.get("cola_2026_percent", "N/A")}%')
        lines.append(f'  SS max benefit at age 70 ({year}): ${ss.get("max_benefit_age_70", "N/A")}/month')
        lines.append(f'  SS max benefit at FRA ({year}): ${ss.get("max_benefit_fra", "N/A")}/month')
        lines.append(f'  SS earnings test limit before FRA ({year}): ${ss.get("earnings_test_limit_before_fra", "N/A")}')
    if ira:
        lines.append(f'  IRA contribution limit under 50 ({year}): ${ira.get("ira_contribution_under_50", "N/A")}')
        lines.append(f'  IRA contribution limit age 50+ ({year}): ${ira.get("ira_contribution_50_plus", "N/A")}')
        lines.append(f'  401(k) contribution under 50 ({year}): ${ira.get("401k_contribution_under_50", "N/A")}')
        lines.append(f'  401(k) contribution age 50-59 and 64 ({year}): ${ira.get("401k_contribution_50_59_64", "N/A")}')
    if rmd:
        lines.append(f'  RMD start age: {rmd.get("start_age", "N/A")} (rises to {rmd.get("start_age_2033_and_after", "N/A")} in 2033)')
    if tax:
        lines.append(f'  Standard deduction single age 65+ ({year}): ${tax.get("standard_deduction_single_65_plus", "N/A")}')
        lines.append(f'  Standard deduction MFJ both 65+ ({year}): ${tax.get("standard_deduction_mfj_both_65_plus", "N/A")}')

    bp = rates.get('benefit_programs', {})
    if bp:
        ssi = bp.get('ssi', {})
        va  = bp.get('va_pension_aid_attendance', {})
        msp = bp.get('medicare_savings_programs', {})
        lis = bp.get('extra_help_lis', {})
        snap = bp.get('snap', {})
        liheap = bp.get('liheap', {})
        if ssi:
            lines.append(f'  SSI federal benefit rate ({year}): ${ssi.get("federal_benefit_rate_individual", "N/A")}/month individual, ${ssi.get("federal_benefit_rate_couple", "N/A")}/month couple')
        if va:
            lines.append(f'  VA Aid and Attendance MAPR ({year}): ${va.get("mapr_veteran_with_spouse_monthly", "N/A")}/month veteran with spouse; net worth limit ${va.get("net_worth_limit", "N/A")}')
        if msp:
            lines.append(f'  Medicare Savings Programs income limits ({year}): QMB ${msp.get("qmb_income_limit_single", "N/A")}/mo single, SLMB ${msp.get("slmb_income_limit_single", "N/A")}/mo single, QI ${msp.get("qi_income_limit_single", "N/A")}/mo single; resource limit ${msp.get("resource_limit_single", "N/A")} single / ${msp.get("resource_limit_couple", "N/A")} couple')
        if lis:
            lines.append(f'  Medicare Extra Help income limit ({year}): ${lis.get("income_limit_individual_annual", "N/A")}/year individual, ${lis.get("income_limit_couple_annual", "N/A")}/year couple; resource limit ${lis.get("resource_limit_single", "N/A")} single / ${lis.get("resource_limit_couple", "N/A")} couple')
        if snap:
            lines.append(f'  SNAP for seniors ({year}): net income limit ${snap.get("net_income_limit_single_monthly", "N/A")}/month single (age {snap.get("elderly_age_threshold", "N/A")}+ exempt from gross income test); resource limit ${snap.get("resource_limit_elderly_or_disabled", "N/A")}')
        if liheap:
            lines.append(f'  LIHEAP eligibility ({year}): federal poverty level ${liheap.get("federal_poverty_level_single_annual", "N/A")}/year single; eligibility range {liheap.get("eligibility_range_pct_fpl", "N/A")}')

    return '\n'.join(lines)


def build_system_prompt(category_key: str = None) -> str:
    """시스템 프롬프트 생성.

    category_key에 따라 목표 단어수 조정:
      A/B (ultra-high CPC, Claude): 1,600-2,000 단어 — 심층 콘텐츠 우선
      C/D (medium CPC, Gemini):     1,200-1,600 단어 — 효율 최적화
    """
    from datetime import datetime
    current_year = datetime.now().year

    # 카테고리별 단어수 목표 (AdSense YMYL 기준 상향)
    if category_key in ('C', 'D'):
        word_target = '1,200-1,600 words'
        deep_dive   = '700-900 words'
    else:
        word_target = '1,600-2,000 words'
        deep_dive   = '950-1,200 words'

    # 연간 공식 수치 주입
    rates = _load_annual_rates()
    rates_block = _build_rates_block(rates)

    return f"""You are a senior content specialist writing for "Healthy After 50" — a practical, fact-driven blog for Americans in their late 50s to mid-70s dealing with Medicare, retirement income, staying independent at home, and managing their health.

IMPORTANT: The current year is {current_year}. Always use {current_year} whenever a year is referenced in titles, headings, or content.

════════════════════════════════════════════════
{rates_block}
════════════════════════════════════════════════

════════════════════════════════════════════════
VOICE AND TONE — YOUR HIGHEST PRIORITY
════════════════════════════════════════════════

Write like a knowledgeable advisor who has helped thousands of people navigate exactly this situation. Not a professor. Not a salesperson. Not a government pamphlet. Someone who knows what goes wrong and what actually works.

NO PERSONAL "I" REFERENCES — ABSOLUTE RULE:
Never write "I", "my", "I've", "I'd", "I tried", "when I", "I remember", or any first-person reference.
This blog does not have a named author persona. Use "you" and "your" throughout.
Replace any urge to say "I've seen this" with: "Many people in this situation find..." or "Benefits advisors often see..."
Replace any urge to say "In my experience" with: "In practice..." or "What typically happens is..."
This rule also applies to hypothetical quotes depicting what the reader might think or say.
BAD: "You might be thinking, 'I can't afford this.'"
GOOD: "If affording this feels impossible right now, you're not alone."
Never construct a sentence where the word "I" appears at all, even inside a quote attributed to the reader.

SHOW EXPERTISE WITHOUT FIRST-PERSON:
BAD:  "When I signed up for Medicare Part B, I almost missed the deadline."
GOOD: "One of the most common and costly Medicare mistakes is missing the Part B enrollment window."

HONESTY ABOUT COMPLEXITY:
When something is genuinely confusing, say so. "This part trips up almost everyone, so read it carefully." Never pretend something is simple when it isn't.

PUSHBACK ON CONVENTIONAL WISDOM (when warranted):
"Most financial advice says wait until 70 to claim Social Security. That's not always right. Here's when it's worth reconsidering." Readers trust writers who acknowledge nuance.

SPECIFIC NUMBERS, NOT ROUND ONES:
Write $1,736, not "around $1,700." Write 2.5%, not "nearly 3%." Use the exact figures from the OFFICIAL FIGURES block above.

SENTENCE VARIETY:
Mix short sentences with longer ones. Short sentences land hard. Longer sentences give context before you move on.

PARENTHETICAL ASIDES (maximum two per article):
"(and yes, that sounds backwards — the explanation is below)" or "(This is where most people stop reading. Don't.)"

DIRECT ADDRESS:
Use "you" and "your" constantly. This article is about the reader, not the topic in the abstract.

WHAT YOU NEVER DO:
Never moralize. Never lecture. Never use the word "journey." State facts. Give options. Let the reader decide.

HONESTY ABOUT COMPLEXITY:
When something is genuinely confusing, say so. "This part trips up almost everyone, so read it carefully." Never pretend something is simple when it isn't.


════════════════════════════════════════════════
ARTICLE STRUCTURE — 4 PARTS
════════════════════════════════════════════════

PART 1: SHARP HOOK (~15% / 200-250 words)
Open with the reader's actual question or anxiety. Not a story. Not a memory. Not a warm-up. The thing they literally Googled.

Make them feel understood in the first two sentences. End with a clear, specific promise of what this article will deliver.

GOOD HOOK EXAMPLES:
"If you're turning 65 in the next few months and still working, you're facing a Medicare decision that has a real deadline — and most HR departments don't warn you about it until it's almost too late."

BAD HOOK EXAMPLES (DO NOT WRITE THESE):
- Any nostalgic story about childhood, summer, or the past
- Generic "retirement can feel overwhelming" openers
- "In today's world..." or "As you approach retirement..."
- Rhetorical questions that answer themselves

PART 2: CONTEXT / EMPATHY (~10% / 150 words)
Acknowledge why this decision is hard or confusing. Give one honest reason why generic advice often fails here. Transition naturally into the main information.

PART 3: DEEP DIVE — MAIN VALUE (~60% / {deep_dive})
- Lead with an <h2> that includes the primary keyword.
- Break into 2-4 sub-sections with <h2> tags.
- Include specific dollar amounts, age thresholds, percentages.
- Include at least one concrete scenario. Write it naturally:
  "Take someone who spent 30 years as a school nurse, earning around $52,000 a year toward the end of her career..."
  NOT: "Meet Linda, 62, a retired school nurse who..."
- Include at least one thing most readers get wrong. Lead with "Most people assume..." and correct it clearly.
- For any set of 3 or more options, costs, or steps: use <ul><li> with <strong>bold lead-in</strong>, colon, explanation.

STATISTICS AND CITATIONS:
IF research_context contains specific data from named sources: cite naturally ("According to a {current_year} SSA report..." or "AARP's survey found that roughly 40% of..."). Only cite what is actually in the research context.
IF research_context is thin: use careful general framing only ("Most estimates suggest..." / "Research generally shows..." / "Benefits advisors generally..."). NEVER fabricate a source, study name, or statistic. NEVER write "according to AARP" if AARP data is not in the research context.

FABRICATION IS THE WORST THING YOU CAN DO — ABSOLUTE PROHIBITION:

RULE 1 — NO DATE + SOURCE COMBINATION:
Never write a specific date (month, day, year) + "report/study/article" + any organization name.
  BANNED: "According to a March 4, 2026, report from Barnstable County..."
  BANNED: "A 2026 study from Johns Hopkins found that X% of..."
  BANNED: "According to a 2025 Harvard report, seniors who... had 43%..."

RULE 2 — NO NON-AUTHORITATIVE SOURCES:
Never cite local governments (counties, cities, townships), senior living facilities,
nursing homes, or assisted living brands as sources of factual claims.
  BANNED: "Harrison Bay Senior Living, in a 2026 article, highlights..."
  BANNED: "According to Barnstable County..."
  BANNED: "Sunrise Senior Living reports that..."

RULE 3 — ONLY THESE SOURCES ARE ALLOWED:
  CDC.gov, NIH.gov, Medicare.gov, SSA.gov, CMS.gov, AARP.org (if in research_context only)
  Use stable, dateless claims: "The CDC recommends..." / "Medicare.gov states..."

RULE 4 — WHEN IN DOUBT, USE THESE SAFE PHRASES:
  GOOD: "Research consistently shows that tai chi reduces fall risk."
  GOOD: "Studies suggest strength training twice a week preserves muscle mass."
  GOOD: "The CDC recommends 150 minutes of moderate activity per week."
  GOOD: "Falls are the leading cause of injury-related deaths among adults 65 and older, according to the CDC."

If you feel the urge to add a specific date, county name, or facility name as a source — STOP. Delete it. Use a safe phrase instead.

MANDATORY OFFICIAL SOURCE LINKS — REQUIRED IN EVERY ARTICLE:
Every article MUST contain at least 2 hyperlinks to official government sources using this exact HTML format:
<a href="URL" rel="noopener noreferrer" target="_blank">anchor text</a>

USE THESE LINKS (pick the ones most relevant to the article topic):

Medicare & Insurance (A/B category or articles mentioning Medicare):
- Medicare appeals:     <a href="https://www.medicare.gov/claims-appeals" rel="noopener noreferrer" target="_blank">Medicare.gov claims and appeals</a>
- Medicare costs:       <a href="https://www.medicare.gov/basics/costs/medicare-costs" rel="noopener noreferrer" target="_blank">official 2026 Medicare costs</a>
- Medicare plan finder: <a href="https://www.medicare.gov/plan-compare" rel="noopener noreferrer" target="_blank">Medicare Plan Finder</a>
- Medicare Part D:      <a href="https://www.medicare.gov/drug-coverage-part-d" rel="noopener noreferrer" target="_blank">Medicare Part D drug coverage</a>
- CMS 2026 costs:       <a href="https://www.cms.gov/newsroom/fact-sheets/2026-medicare-parts-b-premiums-deductibles" rel="noopener noreferrer" target="_blank">CMS 2026 Medicare premiums and deductibles</a>
- SHIP counselors:      <a href="https://www.shiphelp.org" rel="noopener noreferrer" target="_blank">free SHIP Medicare counseling</a>
- Nursing home compare: <a href="https://www.medicare.gov/care-compare/" rel="noopener noreferrer" target="_blank">Medicare Care Compare</a>

Social Security (A/B category or retirement topics):
- Social Security:      <a href="https://www.ssa.gov/benefits/retirement/" rel="noopener noreferrer" target="_blank">Social Security retirement benefits</a>
- My SS account:        <a href="https://www.ssa.gov/myaccount/" rel="noopener noreferrer" target="_blank">my Social Security account</a>
- SS benefit estimator: <a href="https://www.ssa.gov/prepare/estimate-benefits" rel="noopener noreferrer" target="_blank">SSA benefit estimator</a>

Health & Wellness (C/D category — grief, exercise, nutrition, dehydration, mental health, sleep, etc.):
- CDC fall prevention:  <a href="https://www.cdc.gov/falls/index.html" rel="noopener noreferrer" target="_blank">CDC fall prevention for older adults</a>
- CDC physical activity:<a href="https://www.cdc.gov/physicalactivity/basics/older_adults/index.htm" rel="noopener noreferrer" target="_blank">CDC physical activity guidelines for older adults</a>
- CDC healthy aging:    <a href="https://www.cdc.gov/aging/index.html" rel="noopener noreferrer" target="_blank">CDC healthy aging resources</a>
- NIA exercise:         <a href="https://www.nia.nih.gov/health/exercise-physical-activity" rel="noopener noreferrer" target="_blank">NIH exercise and physical activity guide</a>
- NIA grief/loss:       <a href="https://www.nia.nih.gov/health/end-of-life/grief-loss-older-adults" rel="noopener noreferrer" target="_blank">NIH grief and loss in older adults</a>
- NIA nutrition:        <a href="https://www.nia.nih.gov/health/nutrition" rel="noopener noreferrer" target="_blank">NIH nutrition and healthy eating for seniors</a>
- NIA sleep:            <a href="https://www.nia.nih.gov/health/sleep" rel="noopener noreferrer" target="_blank">NIH sleep and aging guide</a>
- MedlinePlus:          <a href="https://medlineplus.gov/seniorshealth.html" rel="noopener noreferrer" target="_blank">MedlinePlus senior health resources</a>

Place these links naturally inside sentences — not as a separate "Resources" section.
Example (Medicare): "You can check your projected benefit at any age using the <a href="https://www.ssa.gov/prepare/estimate-benefits" rel="noopener noreferrer" target="_blank">SSA benefit estimator</a> — it takes about three minutes."
Example (Health): "The <a href="https://www.nia.nih.gov/health/end-of-life/grief-loss-older-adults" rel="noopener noreferrer" target="_blank">NIH grief and loss guide</a> outlines the most common physical symptoms."
NEVER fabricate a URL. Only use the exact URLs listed above.

PART 4: SOFT CLOSE (~10% / 150 words)
- Summarize the one or two most important points in plain language.
- Give one honest sentence about what to do next.
- Warm but not saccharine closing. No "you've worked hard, you deserve this" cliches.
- Do NOT write your own CTA button. It is inserted by code after your content.

PART 5: FAQ (4-5 questions — REQUIRED in every article)
Write 4 to 5 questions your reader would actually type into Google.
Use EXACTLY this HTML format — no variation allowed:

<h2>Frequently Asked Questions</h2>
<h3>Q: [question text]</h3>
<p>A: [answer — 2-4 sentences, include specific numbers or deadlines where relevant]</p>
<h3>Q: [question text]</h3>
<p>A: [answer]</p>

FAQ rules:
- Questions must cover angles NOT already addressed as full sections
- Each answer is self-contained (reader who skips the article still gets value)
- Do NOT copy body paragraphs verbatim — synthesize
- At least one answer must include a specific dollar amount or age threshold

Total target: {word_target} (FAQ word count included in total).
MINIMUM HARD FLOOR: A/B categories must reach at least 1,600 words. C/D must reach at least 1,200 words. Below this, the article will be rejected before publishing.


════════════════════════════════════════════════
FACTUAL ACCURACY — CRITICAL RULES (YMYL CONTENT)
════════════════════════════════════════════════

THE OFFICIAL FIGURES BLOCK ABOVE IS YOUR SINGLE SOURCE OF TRUTH.
When any dollar amount, percentage, or threshold is in that block, use it exactly. Do NOT rely on memory or training data for annual figures.

MEDICARE PART D — CRITICAL {current_year} FACTS:
- The coverage gap (donut hole) was ELIMINATED effective January 1, 2025. Do NOT describe it as something that still exists.
- In {current_year}, Part D has a hard $2,000/year out-of-pocket cap. See exact figures above.
- The old $5,030 catastrophic threshold is OBSOLETE — do not cite it.
- Extra Help (LIS) still exists. But it's for lower copays/premiums, NOT gap protection.

RMD (Required Minimum Distributions):
- SECURE 2.0 Act: RMD age is 73 for anyone who turned 72 after Dec 31, 2022.
- Future change: RMD age rises to 75 starting in 2033.
- Do NOT write "RMDs begin at 72" — that is outdated.

SOCIAL SECURITY FULL RETIREMENT AGE (FRA):
- Born 1943-1954: FRA is 66.
- Born 1955-1959: FRA is 66 + 2 months per birth year.
- Born 1960 or later: FRA is 67.
- Do NOT write "full retirement age is 65."

IRA / 401(K) LIMITS: Use the exact figures from the OFFICIAL FIGURES block above.
Do NOT write the IRA limit is $6,000 — that was 2019-2022.

════════════════════════════════════════════════
STRICT LANGUAGE RULES — ABSOLUTE, NEVER BREAK
════════════════════════════════════════════════

ENGLISH ONLY. Every character must be English or standard ASCII punctuation. Zero tolerance for non-English characters (no Chinese, Japanese, Korean, Arabic, accented letters).

BANNED WORDS — NEVER USE ANY OF THESE:
crucial, delve, moreover, leverage, utilize, it's important to note, in conclusion, furthermore, navigate (metaphorical), embark, seamlessly, game-changer, transformative, holistic, robust, dive into, unpack, look no further, in today's world, ever-changing landscape, journey, empower, proactive, innovative, cutting-edge, best practices, going forward, touch base

BANNED SENTENCE OPENERS — NEVER START A SENTENCE WITH THESE:
"The good news is," / "The bad news is," / "Simply put," / "At the end of the day," / "It goes without saying," / "Needless to say," / "The bottom line is," / "It's worth noting that," / "It's no secret that," / "Make no mistake," / "Rest assured,"

PUNCTUATION:
NEVER use em dashes (—) or en dashes (–) anywhere. When you feel the urge to use an em dash:
  Option A — End the sentence. Start a new sentence.
  Option B — Rewrite the clause so no dash is needed.
Do NOT replace em dashes with commas if doing so creates a comma splice.
Use contractions naturally: it's, you'll, we've, don't, that's, you'd.

SCANNABILITY — MOBILE-FIRST, SENIOR READERS:
Maximum 3 sentences per paragraph. One idea per paragraph. Never stack two long paragraphs back to back.
After every 2-3 paragraphs, insert either a <h2> heading, a <ul> list, or a single-sentence "bridge" paragraph.
This creates natural white space for ad placement and prevents reader fatigue.
Any set of 3 or more items MUST use <ul><li> with bold lead-ins.
Use <h2> headings at least every 200 words (not 250).
Target average sentence length: 14-18 words.
Short punchy sentences (under 10 words) should appear at least once per section. They land hard.

MONETIZATION:
You MAY reference official resources (SSA.gov, Medicare.gov, my Social Security account). Frame the comparison tool as faster and easier, not a replacement.
Do NOT write your own CTA button. Do NOT tell readers to call any 1-800 number.


════════════════════════════════════════════════
OUTPUT FORMAT
════════════════════════════════════════════════
Return ONLY a valid JSON object. No markdown fences. No extra text. No preamble.

Schema:
{{
  "title": "SEO H1 title — include primary keyword, under 65 characters",
  "meta_description": "Under 155 characters. Contains primary keyword. Written as a direct answer or strong promise — not a vague teaser.",
  "html_content": "Full post as HTML. Use <h2>,<p>,<ul>,<li>,<strong>,<em> only. No <html><head><body> tags. No inline styles.",
  "tags": ["tag1","tag2","tag3","tag4","tag5"],
  "image_query": "Unsplash search query — realistic scene, not stock-photo cliche. Example: 'older man reviewing papers at kitchen table morning light'"
}}"""


def build_user_prompt(category_key, category_info, primary_keyword,
                      supporting_keywords, hook_type, hook_angle,
                      research_context: str = '',
                      word_target: str = '1,400-1,800 words',
                      deep_dive: str = '850-1,000 words') -> str:
    sup_kw = '\n'.join(f'  - {kw}' for kw in supporting_keywords)

    # 카테고리 C (Aging in Place): 제품 가격 범위 명시 지시
    # 샤워 의자, 안전 손잡이, 경사로 등 실제 구매가 포함된 주제
    if category_key == 'C':
        price_instruction = (
            'REQUIRED: This category covers products people actually buy. '
            'Include realistic price ranges (e.g., "Basic models start around $35, '
            'while bariatric-rated options run $150-$300"). '
            'Do NOT use vague language like "affordable" or "expensive" — give actual dollar ranges.\n  '
        )
    else:
        price_instruction = ''
    research_block = ''
    if research_context:
        research_block = f"""
REAL-TIME RESEARCH DATA (cite naturally when specific data is present — do NOT fabricate sources):
{research_context}

"""
    return f"""Write a full blog post for "Healthy After 50" following all system prompt rules exactly.
{research_block}
CATEGORY: {category_info['name']}
PRIMARY KEYWORD (must appear in H1 title and at least one H2): "{primary_keyword}"
SUPPORTING KEYWORDS (weave in naturally — never forced, never repeated more than twice):
{sup_kw}

────────────────────────────────────────
HOOK INSTRUCTION (Part 1 — 200-250 words):
────────────────────────────────────────
Hook type: {hook_type}
Suggested angle (use as a starting point — develop it, make it specific and earned):
"{hook_angle}"

Open with the reader's real situation right now. Do NOT open with a story, a memory, or any nostalgic reference. Do NOT open with generic statements like "retirement can feel overwhelming."

End Part 1 with a clear, specific promise of what this article delivers.

────────────────────────────────────────
CONTEXT / EMPATHY (Part 2 — 150 words):
────────────────────────────────────────
Acknowledge why this topic is genuinely confusing or difficult. One honest reason why generic advice often fails here. Transition naturally into the main content.

────────────────────────────────────────
DEEP DIVE (Part 3 — {deep_dive}):
────────────────────────────────────────
- First <h2> must include the primary keyword "{primary_keyword}".
- Break into 2-4 sub-sections with <h2> tags.
- Include specific dollar amounts, age thresholds, or percentages (from research context if available — otherwise use general framing only).
  {price_instruction}- One concrete scenario written naturally (NOT "Meet Linda, 62..." — write it as "Take someone who worked as...").
- At least one "Most people assume..." correction.
- Supporting keywords woven in naturally.

────────────────────────────────────────
SOFT CLOSE (Part 4 — 200 words):
────────────────────────────────────────
- Summarize 1-2 most important takeaways in plain language.
- One honest next step (may include checking SSA.gov, Medicare.gov, or the my Social Security account).
- Warm but not cliche closing. No "you've worked hard, you deserve this."
- Do NOT write a CTA button — it is inserted by code.

────────────────────────────────────────
SEO REQUIREMENTS:
────────────────────────────────────────
- H1 title: must contain primary keyword, under 65 characters.
- At least 2 H2 headings contain keywords.
- Total word count: {word_target}.
- meta_description: direct answer or strong promise, under 155 characters, contains primary keyword.
- image_query: realistic scene (example: "older couple reviewing documents at kitchen table") — NOT stock-photo cliches like "happy senior couple smiling at sunset."

Return ONLY valid JSON per the schema in the system prompt. No preamble. No commentary. JSON only."""


# ─────────────────────────────────────────
# JSON 파싱
# ─────────────────────────────────────────

def _close_html_tags(html: str) -> str:
    """잘린 HTML에서 열린 태그를 닫아 파싱 가능한 상태로 복구.
    BeautifulSoup이 내부적으로 닫아주지만, 명시적으로 닫아두면
    태그 중첩 오류로 인한 불완전한 렌더링을 방지할 수 있다."""
    from bs4 import BeautifulSoup
    if not html.strip():
        return html
    soup = BeautifulSoup(html, 'html.parser')
    return str(soup)


def _parse_json(raw: str) -> dict:
    """AI 응답 JSON 파싱. 잘린 응답 3단계 복구 시도:
      1단계: 그대로 파싱
      2단계: 마지막 완전한 문자열 필드까지 잘라서 닫기
      3단계: html_content 필드가 있으면 태그 자동 닫기 후 재조립
    """
    clean = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    clean = re.sub(r'\s*```$', '', clean).strip()
    # JSON 블록만 추출
    start = clean.find('{')
    end = clean.rfind('}')
    if start != -1 and end != -1:
        clean = clean[start:end+1]

    # ── 1단계: 직접 파싱 ──────────────────────────────────────────
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        logger.warning(f'JSON 파싱 오류 ({e}) — 응답이 잘렸을 수 있음. 복구 시도 1/2...')

    # ── 2단계: 마지막 완전한 문자열 필드까지 잘라서 닫기 ──────────
    # html_content가 중간에 잘린 경우: 마지막 닫힌 </p> 또는 </li> 뒤를 기준
    truncate_patterns = [r'</p>\s*"', r'</li>\s*"', r'</h[1-6]>\s*"', r'"']
    for pat in truncate_patterns:
        m = None
        for mm in re.finditer(pat, clean):
            m = mm  # 마지막 매치
        if m:
            candidate = clean[:m.start() + (len(m.group()) - 1)]  # " 직전까지
            # 열린 string 값 닫기 + JSON object 닫기
            candidate = re.sub(r',\s*$', '', candidate.rstrip())
            for suffix in ['"}', '"]}', '"}]', '"}}']:
                try:
                    result = json.loads(candidate + suffix)
                    logger.warning(f'JSON 2단계 복구 성공 (suffix: {suffix!r})')
                    # html_content 태그 정리
                    if 'html_content' in result:
                        result['html_content'] = _close_html_tags(result['html_content'])
                    return result
                except json.JSONDecodeError:
                    continue

    # ── 3단계: 부분 파싱 — 열린 string 포함 허용 ────────────────
    logger.warning('JSON 3단계 복구 시도 — 부분 필드 추출...')
    partial = {}
    for field in ('title', 'meta_description', 'html_content', 'tags', 'image_query'):
        # 1) 완전히 닫힌 string 값 추출 시도
        closed_pat = rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        m = re.search(closed_pat, clean, re.DOTALL)
        if m:
            partial[field] = m.group(1).replace('\\"', '"').replace('\\n', '\n')
            continue
        # 2) 열린(잘린) string 값 — 필드 선언 이후 끝까지 추출
        if field == 'html_content':
            open_pat = rf'"{field}"\s*:\s*"(.*)'
            m2 = re.search(open_pat, clean, re.DOTALL)
            if m2:
                # 잘린 HTML 값 → 언이스케이프 후 태그 닫기
                partial[field] = _close_html_tags(
                    m2.group(1).replace('\\"', '"').replace('\\n', '\n')
                )

    if partial.get('html_content'):
        partial.setdefault('title', '')
        partial.setdefault('meta_description', '')
        logger.warning(f'JSON 3단계 부분 복구 성공: {list(partial.keys())}')
        return partial

    raise RuntimeError(f'JSON 파싱 실패 (응답 {len(raw)}자): 3단계 모두 실패')


# ─────────────────────────────────────────
# 영어 전용 검증 (CJK / 비ASCII 감지 → 즉시 차단)
# ─────────────────────────────────────────

def _assert_english_only(post_data: dict) -> None:
    """제목·본문에 CJK(한중일) 또는 비ASCII 문자가 있으면 RuntimeError 발생"""
    CJK_RANGE = re.compile(
        r'[　-鿿'   # CJK 통합 한자, 한중일 기호
        r'ꀀ-꒏'    # Yi
        r'가-퟿'    # 한글
        r'豈-﫿'    # CJK 호환 한자
        r'＀-￯]'   # 전각 문자
    )
    fields = {
        'title': post_data.get('title', ''),
        'html_content': post_data.get('html_content', ''),
        'meta_description': post_data.get('meta_description', ''),
    }
    for field, text in fields.items():
        found = CJK_RANGE.findall(text)
        if found:
            sample = ''.join(found[:10])
            raise RuntimeError(
                f'[ENGLISH GUARD] 비영어 문자 감지 ({field}): "{sample}" — 재생성 필요'
            )


# ─────────────────────────────────────────
# 연도 자동 교정 (본문 생성 후 2차 방어)
# ─────────────────────────────────────────

def _sanitize_year(post_data: dict) -> dict:
    """제목/메타 연도 교정 + 본문 참조 연도(title 끝 / 발행 컨텍스트)만 교정.

    v1 문제: html_content 전체 치환 → 역사적 사실 날짜 오염
      예) "SECURE 2.0 was signed in 2022" → "...in 2026"
          "Medicare Part D started in 2006" → "...in 2026"

    v2 수정:
      - title / meta_description: 과거 연도 전체 교정 (제목에 올드 연도 금지)
      - html_content: '발행 컨텍스트 연도'만 교정
            패턴 A: 제목 수준 참조 — "in {PAST_YEAR}" 이 문장 마지막 단어이거나
                    heading 태그 안에 있는 경우
            패턴 B: "as of {PAST_YEAR}" / "in {PAST_YEAR}," 형태
        역사적 날짜는 건드리지 않음 (예: "signed in 2022", "established in 2006")
    """
    from datetime import datetime
    current_year = str(datetime.now().year)
    current_int  = int(current_year)

    # ── 1) title / meta: 전체 과거 연도 교정 ─────────────────────────
    for field in ('title', 'meta_description'):
        text = post_data.get(field, '')
        if not text:
            continue
        original = text
        for past_year in range(2020, current_int):
            text = text.replace(str(past_year), current_year)
        if text != original:
            logger.warning(f'[YEAR SANITIZE] {field}: 과거 연도 → {current_year}')
        post_data[field] = text

    # ── 2) html_content: h1/h2 heading 태그 안 연도만 교정 ──────────
    # 본문 body 텍스트는 건드리지 않음 — 역사적 사실 날짜 보존
    # (예: "SECURE 2.0 was signed in 2022", "Medicare started in 2006")
    html = post_data.get('html_content', '')
    if not html:
        return post_data

    original_html = html
    for past_year in range(2020, current_int):
        py = str(past_year)
        # heading 태그(<h1>/<h2>) 내부 연도만 교정 — <h3> 이하는 보존
        html = re.sub(
            rf'(<h[12][^>]*>[^<]{{0,150}}){py}([^<]{{0,50}}<\/h[12]>)',
            lambda m, cy=current_year: m.group(1) + cy + m.group(2),
            html,
        )

    if html != original_html:
        logger.warning('[YEAR SANITIZE] html_content: heading 연도 교정')
    post_data['html_content'] = html
    return post_data


def _sanitize_style(post_data: dict) -> dict:
    """AI 특유의 문체 패턴 제거 — em dash 문맥 기반 교정 (v2.0)
    v1 문제: em dash → 쉼표 단순 치환 → comma splice(문법 오류) 발생
    v2 개선: 뒤에 대문자 오면 마침표로 분리 / 소문자면 공백으로 연결"""
    fields = ['title', 'html_content', 'meta_description']
    for field in fields:
        text = post_data.get(field, '')
        if not text:
            continue
        original = text
        # 패턴 1: [단어] — [대문자] → [단어]. [대문자] (새 문장 시작)
        text = re.sub(r'\s*[—]\s*(?=[A-Z])', '. ', text)
        # 패턴 2: [단어] — [소문자/숫자] → [단어] [소문자] (삽입구 공백 처리)
        text = re.sub(r'\s*[—]\s*', ' ', text)
        # en dash → 일반 하이픈
        text = re.sub(r'\s*[–]\s*', '-', text)
        # 이중 공백 정리
        text = re.sub(r' {2,}', ' ', text).strip()
        if text != original:
            logger.warning(f'[STYLE SANITIZE] {field}에서 dash 교정')
        post_data[field] = text
    return post_data


# ─────────────────────────────────────────
# 최소 단어수 검증 (응답 잘림 감지)
# ─────────────────────────────────────────

def _assert_min_words(post_data: dict, min_words: int = 900) -> None:
    """html_content 단어수가 min_words 미만이면 잘림으로 판단 → RuntimeError"""
    from bs4 import BeautifulSoup
    html = post_data.get('html_content', '')
    text = BeautifulSoup(html, 'html.parser').get_text()
    word_count = len(text.split())
    logger.info(f'[WORD COUNT] {word_count}단어')
    if word_count < min_words:
        raise RuntimeError(
            f'[SHORT CONTENT] {word_count} words (minimum {min_words} required, response likely truncated)'
        )


# ─────────────────────────────────────────
# Banned Phrase 가드 (HARD/SOFT 2단계)
# ─────────────────────────────────────────

# HARD: 순수 AI 특유 표현 → 감지 시 RuntimeError → 재시도
# Gemini가 Claude보다 자주 쓰는 표현도 포함 (실측 기반)
BANNED_HARD = {
    'crucial', 'delve', 'seamlessly', 'embark', 'game-changer',
    'game changer', 'transformative', 'holistic', 'robust',
    'cutting-edge', 'cutting edge', 'going forward', 'journey',
    'dive into', 'unpack', 'look no further',
    # Gemini 추가 패턴 — 시스템 프롬프트에 이미 금지되었으나 Gemini가 무시하는 단어
    'empower', 'proactive', 'leverage',
}

# SOFT: 자연스러운 영어에도 등장 → 경고 로그만 남기고 통과
BANNED_SOFT = {
    'the good news is', 'the bad news is', 'simply put',
    'at the end of the day', 'it goes without saying',
    'needless to say', 'the bottom line is', "it's worth noting",
    "it's no secret", 'make no mistake', 'rest assured',
    'in conclusion', 'furthermore', 'moreover', 'utilize',
}


def _check_banned_phrases(post_data: dict) -> None:
    """HARD 금지 문구 감지 시 RuntimeError / SOFT는 경고 후 통과"""
    text = post_data.get('html_content', '').lower()

    hard_found = [p for p in BANNED_HARD if p in text]
    if hard_found:
        raise RuntimeError(f'[BANNED-HARD] detected, retry needed: {hard_found}')

    soft_found = [p for p in BANNED_SOFT if p in text]
    if soft_found:
        logger.warning(f'[BANNED-SOFT] 감지됨 (통과): {soft_found}')


# ─────────────────────────────────────────
# MAIN GENERATE FUNCTION
# ─────────────────────────────────────────

def generate_post(
    category_key: str = None,
    primary_keyword: str = None,
    supporting_keywords: list = None,
) -> dict:
    if category_key is None:
        category_key, category_info = get_category_for_today()
    else:
        category_info = CATEGORIES[category_key]

    # 외부에서 키워드 전달 시 그대로 사용 (60일 이력 적용된 collector 결과)
    # 미전달 시 랜덤 샘플링으로 폴백 (단독 실행·테스트 호환)
    if primary_keyword is None:
        keywords = get_keywords_for_category(category_key, n=4)
        primary_keyword = keywords[0]
        supporting_keywords = keywords[1:]
    elif supporting_keywords is None:
        supporting_keywords = []
    # 30일 쿨다운 앵글 제외하여 선택
    used_angles = get_used_hook_angles()
    hook = get_hook_for_category(category_key, used_angles=used_angles)
    logger.info(f'Hook Angle: "{hook["hook_angle"]}" (쿨다운 제외: {len(used_angles)}개)')

    # 웹 리서치 (Tavily) — 최신 데이터 수집
    logger.info(f'[RESEARCH] 웹 리서치 중: "{primary_keyword}"')
    research_context = fetch_research(primary_keyword)

    # 카테고리별 목표 단어수 결정
    # min_words는 publish_governor.py의 HARD 임계치(hard_min_wc)와 반드시 일치시킬 것 —
    # 여기가 governor보다 낮으면 900~1199단어(A/B) 구간에서 재시도 없이 통과된 글이
    # 최종 게이트에서 뒤늦게 차단되어 파이프라인 전체가 그대로 실패로 끝남 (재시도 기회 낭비)
    if category_key in ('C', 'D'):
        word_target = '1,100-1,400 words'
        deep_dive   = '650-800 words'
        min_words   = 1000   # publish_governor.py hard_min_wc(C/D)와 동일
    else:
        word_target = '1,400-1,800 words'
        deep_dive   = '850-1,000 words'
        min_words   = 1200   # publish_governor.py hard_min_wc(A/B)와 동일

    system_prompt = build_system_prompt(category_key=category_key)
    base_user_prompt = build_user_prompt(
        category_key, category_info, primary_keyword,
        supporting_keywords, hook['hook_type'], hook['hook_angle'],
        research_context=research_context,
        word_target=word_target,
        deep_dive=deep_dive,
    )

    logger.info(f'카테고리: {category_key} / {category_info["name"]}')
    logger.info(f'Primary Keyword: {primary_keyword}')
    logger.info(f'Hook Type: {hook["hook_type"]}')
    logger.info(f'목표 단어수: {word_target}')

    # 카테고리별 모델 라우팅 (A/B→Claude, C/D→Gemini)
    writer = EngineLoader().get_writer(category_key=category_key)

    post_data = None
    success = False  # 검증까지 전부 통과한 시도가 있었는지 — post_data 존재 여부만으론 부족
    feedback = ''  # 이전 시도 실패 이유 → 다음 시도에 피드백
    for attempt in range(1, 4):  # 최대 3회 시도
        # 재시도 시 실패 원인을 프롬프트 앞에 명시 → 맹목적 반복 방지
        if feedback:
            user_prompt = f"PREVIOUS ATTEMPT FAILED. Do NOT use these in your response: {feedback}\n\n{base_user_prompt}"
        else:
            user_prompt = base_user_prompt

        raw = writer.write(user_prompt, system=system_prompt)
        if not raw:
            logger.warning(f'빈 응답 (시도 {attempt}/3)')
            continue
        try:
            candidate = _parse_json(raw)
            candidate = _sanitize_year(candidate)       # 과거 연도 강제 교정
            candidate = _sanitize_style(candidate)      # em dash 문맥 기반 교정
            _assert_min_words(candidate, min_words=min_words) # 잘림 감지 (카테고리별)
            _assert_english_only(candidate)             # CJK 문자 차단
            _check_banned_phrases(candidate)            # HARD 금지 문구 차단
            post_data = candidate  # 검증 전부 통과한 경우에만 채택
            success = True
            break
        except RuntimeError as e:
            feedback = str(e)
            logger.warning(f'실패 (시도 {attempt}/3): {e}')

    if not success:
        raise RuntimeError(f'콘텐츠 생성 실패: 3회 모두 실패 (마지막 사유: {feedback})')
    post_data['category_key']   = category_key
    post_data['category_info']  = category_info
    post_data['primary_keyword'] = primary_keyword
    post_data['_hook']          = hook   # auto_publish가 이력 기록에 사용

    return post_data
