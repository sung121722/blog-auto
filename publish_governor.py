"""
publish_governor.py — 발행 전 최종 품질 게이트

파이프라인 위치:
  generate_post() → [publish_governor] → publisher_bot.publish()

두 계층으로 나뉨:
  HARD_BLOCK : 발행 즉시 차단 → PublishBlocked 예외 발생
  SOFT_WARN  : 경고 로그 기록 + 통과 (수동 확인 권장)

HARD_BLOCK 조건:
  1. 최소 단어수 미달 (A/B: 1,200 / C/D: 1,000) — JSON 잘림 감지
  2. CJK / 비ASCII 문자 — 한중일 문자 혼입
  3. BANNED_HARD 문구 — 순수 AI 특유 표현
  4. 사실 오류 패턴 — RMD 나이 오류, 잘못된 법률 연도 등
  5. 빈 제목 / 빈 HTML
  6. 개인참조 (I watched/saw/tried 등) 1회 이상 — 0회 정책 (AdSense Helpful Content)
  7. 연간 수치 stale 감지 — annual_rates.json 기반 이전 연도 수치 사용 차단

SOFT_WARN 조건:
  1. 목표 단어수 미달 (1,400) — 짧은 글
  2. 제목 65자 초과
  3. 메타 디스크립션 155자 초과
  4. 태그 8개 초과 (Blogger API 400 오류 임계치)
  5. BANNED_SOFT 문구
  6. 더미 링크 (example.com) — publisher_bot이 비활성 버튼으로 이미 처리
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_DIR  = Path(__file__).parent
_LOG_DIR   = _BASE_DIR / 'logs'
_DRAFT_DIR = _BASE_DIR / 'drafts'
_GOV_LOG   = _LOG_DIR / 'governor.jsonl'   # 누적 품질 이력 (JSON Lines)

# ─── HARD 금지 문구 (AI 특유 표현) ──────────────────────────────
BANNED_HARD = {
    'crucial', 'delve', 'seamlessly', 'embark', 'game-changer',
    'game changer', 'transformative', 'holistic', 'robust',
    'cutting-edge', 'cutting edge', 'going forward', 'journey',
    'dive into', 'unpack', 'look no further',
}

# ─── SOFT 경고 문구 ───────────────────────────────────────────
BANNED_SOFT = {
    'the good news is', 'the bad news is', 'simply put',
    'at the end of the day', 'it goes without saying',
    'needless to say', 'the bottom line is', "it's worth noting",
    "it's no secret", 'make no mistake', 'rest assured',
    'in conclusion', 'furthermore', 'moreover', 'utilize',
}

# ─── CJK / 비ASCII 감지 패턴 ─────────────────────────────────
_CJK_RE = re.compile(
    r'[　-鿿'   # CJK 통합 한자, 한중일 기호
    r'ꀀ-꒏'
    r'가-퟿'    # 한글
    r'豈-﫿'
    r'＀-￯]'   # 전각 문자
)

# ─── 사실 오류 패턴 (HARD) ───────────────────────────────────
# 규칙: 처방적 / 현재 시제 문맥의 오류만 차단
#       역사적 서술("old rule was 72", "shifted from 72")은 통과
#
# 커버 영역:
#   1. RMD 나이 오류     — SECURE 2.0 이후 73세 (2023~)
#   2. Social Security FRA 오류 — 1960년생 이후 67세
#   3. Medicare Part D donut hole — 2025년부터 폐지
#   4. IRA 기여 한도 저가 표기
#   5. Coverage gap 현재 시제
#   6. 가짜 연구 인용 — 기관+연도+% 조합
#   4. IRA 기여 한도 저가 표기 — 2024+ 7,000달러 (50세↑ 8,000)

_FACTUAL_ERROR_PATTERNS = [
    # ── 1. RMD ──────────────────────────────────────────────────
    (
        # "RMD begins/starts at age 72" / "RMD age is 72"
        re.compile(
            r'\b(?:rmd|required minimum distribution)s?\b.{0,80}'
            r'\b(?:begins?|starts?|age is|starts? at)\b.{0,30}\b72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD age stated as 72 — SECURE 2.0 changed it to 73 starting 2023'
    ),
    (
        # "start/begin/take your RMD at age 72"
        re.compile(
            r'\b(?:start|begin|take|taking)\b.{0,30}'
            r'\b(?:rmd|required minimum distribution)s?\b.{0,30}'
            r'\bat age 72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD age stated as 72 — correct age is 73 under SECURE 2.0'
    ),
    (
        # "must/required to start RMDs at 72"
        re.compile(
            r'\b(?:must|required to|have to|need to)\b.{0,30}'
            r'\b(?:start|begin|take)\b.{0,30}'
            r'\b(?:rmd|required minimum distribution)s?\b.{0,30}\b72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD start requirement stated as age 72 — correct is 73 under SECURE 2.0'
    ),

    # ── 2. Social Security Full Retirement Age ───────────────────
    # FRA는 출생 연도에 따라 다름. 1960년생 이후 = 67세.
    # BAD: "full retirement age is 65" / "FRA is 65" (폐지된 나이)
    # OK:  "FRA used to be 65" / "old full retirement age of 65"
    (
        re.compile(
            r'\b(?:full retirement age|fra)\b.{0,60}'
            r'\bis\b.{0,20}\b65\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Full Retirement Age stated as 65 — FRA for those born 1960+ is 67'
    ),
    (
        # "claim Social Security at full retirement at 65"
        re.compile(
            r'\b(?:claim|receive|collect)\b.{0,40}'
            r'\b(?:social security|ss benefits)\b.{0,40}'
            r'\b(?:full|full retirement)\b.{0,20}\b65\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Social Security full benefit age stated as 65 — current FRA is 66-67 depending on birth year'
    ),

    # ── 3. Medicare Part D Donut Hole ────────────────────────────
    # 2025년부터 폐지됨 (IRA 2022). 2025+ 글에서 "donut hole" 존재 주장 차단.
    # BAD: "you will fall into the donut hole" (현재 시제)
    # OK:  "the donut hole used to apply" / "before 2025, the donut hole"
    (
        re.compile(
            r'\b(?:fall into|enter|hit|reach)\b.{0,30}'
            r'\b(?:the\s+)?(?:donut|doughnut)\s+hole\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Medicare Part D donut hole stated as active — it was eliminated in 2025 (IRA 2022)'
    ),

    # ── 4. IRA 기여 한도 ─────────────────────────────────────────
    # 2024+: 기본 $7,000 / 50세 이상 $8,000 (캐치업 $1,000)
    # BAD: "IRA contribution limit is $6,000" / "contribute up to $6,000"
    # OK:  "the limit was $6,000 in 2022"
    (
        re.compile(
            r'\b(?:ira|roth ira|traditional ira)\b.{0,60}'
            r'\b(?:limit is|contribute up to|maximum of|up to)\b.{0,20}'
            r'\$6[,.]?000\b',
            re.IGNORECASE | re.DOTALL
        ),
        'IRA contribution limit stated as $6,000 — 2024+ limit is $7,000 ($8,000 age 50+)'
    ),

    # ── 5. Medicare Part D Coverage Gap (Donut Hole) ─────────────
    # IRA 2022 기준: 2025년부터 coverage gap 완전 폐지.
    # 2025+에서 모든 Part D 가입자는 연간 본인부담 $2,000 상한 적용.
    #
    # BAD: "coverage gap kicks in" / "you hit the coverage gap"
    #      "fall into the coverage gap" / "enter the coverage gap"
    # OK:  "coverage gap was eliminated" / "before 2025, the coverage gap"
    #      "Extra Help protects against the old coverage gap"
    (
        re.compile(
            r'\b(?:coverage|spending)\s+gap\b.{0,80}'
            r'\b(?:kicks?\s+in|you\b.{0,15}\b(?:hit|reach|enter)\b'
            r'|fall(?:s|ing)?\s+into|still\s+(?:exists?|applies?|has))\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Coverage gap (donut hole) stated as active — eliminated Jan 1 2025 (IRA 2022). '
        'In 2025+, Part D has a $2,000 annual OOP cap with no gap phase.'
    ),
    (
        # "coverage gap where you pay more" / "coverage gap costs you"
        re.compile(
            r'\b(?:coverage|spending)\s+gap\s+(?:where|that|which)\b.{0,60}'
            r'\b(?:pay(?:ing)?|cost(?:ing)?|owe)\b.{0,30}\b(?:more|out.of.pocket)\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Coverage gap described as a current cost burden — gap was eliminated Jan 1 2025.'
    ),

    # ── 6. 가짜 연구 인용 (Hallucinated Citation) — 3가지 패턴 차단 ──
    #
    # [6-A] 연도 + study/report + 기관명 조합
    # BAD: "A 2026 study from Johns Hopkins found..."
    # BAD: "According to a March 4, 2026, report from Barnstable County..."
    (
        re.compile(
            r'\b(?:a |an )?(?:(?:january|february|march|april|may|june|july|august|'
            r'september|october|november|december)\s+\d{1,2},?\s+)?'
            r'20\d{2}[,]?\s+(?:study|report|research|trial|article|survey|analysis)\s+'
            r'(?:from|by|at|conducted by|published by)\s+\S',
            re.IGNORECASE | re.DOTALL
        ),
        '[6-A] 날짜/연도 + report/study + 기관 조합 감지 — 할루시네이션 위험. '
        '"Research suggests..." 또는 CDC/SSA/Medicare.gov 직접 링크 사용'
    ),
    #
    # [6-B] 비공인 기관 인용 — senior living 업체, county, 로컬 기관
    # BAD: "Harrison Bay Senior Living, in a 2026 article, highlights..."
    # BAD: "According to Barnstable County..."
    # OK:  "According to the CDC..." / "Medicare.gov states..."
    # OK:  "According to Medicaid rules, nursing home residents must..." (공식 제도명이 이미 인용 대상)
    # OK:  "A nursing home stay often shows..." (일반적 서술, 특정 시설/기관 인용 아님)
    # v2 수정: 혜택정보 키워드(Medicaid/VA 등) 추가 후 오탐 다발 확인되어 두 가지 가드 추가
    #   1. 인용 동사와 기관어 사이에 공식 출처명(medicaid/medicare/cdc 등)이 있으면 제외
    #   2. 기관어 앞에 관사(a/an/the)가 오면 일반 명사로 판단해 제외 (실제 시설명 인용이 아님)
    (
        re.compile(
            # 패턴A: 동사 먼저 → 기관명 (According to Barnstable County)
            r'(?:'
            r'\b(?:according to|per|as noted by|as stated by|found that|reports? that)\b'
            r'(?:(?!medicaid|medicare|cdc\b|ssa\b|cms\b|nih\b|\.gov|official).){0,80}'
            r'\b(?:senior living|assisted living|memory care|nursing home|'
            r'county|township|borough|village|city of|town of)\b'
            r'|'
            # 패턴B: 기관명 먼저 → 동사 (Harrison Bay Senior Living ... highlights)
            r'(?<!\ba )(?<!\ban )(?<!\bthe )'
            r'\b(?:senior living|assisted living|memory care|nursing home)\b'
            r'[^\n]{0,80}'
            r'\b(?:highlights?|notes?|reports?|finds?|shows?|suggests?|'
            r'recommends?|emphasize?s?|points? out)\b'
            r')',
            re.IGNORECASE
        ),
        '[6-B] 비공인 기관 인용 감지 (senior living업체 / 지방정부) — '
        'CDC, NIH, Medicare.gov, SSA.gov 등 공식 출처만 인용 가능'
    ),
    #
    # [6-C] 연도 + 기관명 + 구체적 % 수치 조합 (가장 위험한 패턴)
    # BAD: "A 2026 Harvard report found 43% of seniors..."
    (
        re.compile(
            r'\b(?:a |an )?20\d{2}\s+(?:study|report|research|trial)\s+'
            r'(?:from|by|at|conducted by)\s+'
            r'(?:johns?\s+hopkins?|harvard|mayo\s+clinic|stanford|cdc|nih|aarp|'
            r'university\s+of|american\s+(?:heart|college|medical)|'
            r'national\s+institute|department\s+of)\b',
            re.IGNORECASE | re.DOTALL
        ),
        '[6-C] 연도+기관+연구 조합 — 할루시네이션 고위험. '
        '"Research consistently shows..." 사용'
    ),

    # ── 7. 개인참조 2회 초과 (Personal Reference > 1) ────────────
    # 규칙: 글 당 정확히 1회만 허용 ("I watched a colleague..." 수준).
    # BAD: "I watched..." + "In one case I saw..." (2회)
    # OK:  "I watched a colleague once..." (1회만, 이후 I/my/I've 없음)
    # 감지: \b(i watched|i saw|i know|i once|i always|i remember|i tried|
    #            i learned|i've|i retired|when i|i helped|i've sat)\b
    # 2회 이상이면 HARD BLOCK
]

# 별도 처리 — 개인참조 감지 (0회 허용 정책: 프롬프트가 NO I-REFERENCE로 변경됨)
_PERSONAL_REF_RE = re.compile(
    # "How do/would I know...?"는 독자가 던지는 FAQ 질문 형식(1인칭 경험 서술 아님) — 오탐 제외
    r'\b(i\s+watched|i\s+saw|(?<!how do )(?<!how would )(?<!how does one )i\s+know|i\s+once|i\s+always|i\s+remember'
    r'|i\s+tried|i\s+learned|i\'ve|i\s+retired|when\s+i\s|i\s+helped'
    r'|i\'ve\s+sat|i\s+spent|i\s+worked|i\s+have\s+seen|i\s+have\s+watched'
    r'|i\s+can\'t|i\s+cannot|i\s+would|i\s+will|i\s+think|i\s+believe'
    r'|i\s+suggest|i\s+recommend|i\s+finally|when\s+i\s+finally'
    r'|i\s+almost|i\s+found|i\s+discovered|i\s+realized)\b',
    re.IGNORECASE
)

# ─── 연간 수치 stale 감지 ─────────────────────────────────────
# annual_rates.json의 이전 연도 수치가 글에 등장하면 HARD BLOCK
def _load_stale_figure_checks() -> list:
    """annual_rates.json 기반 이전 연도 수치 감지 패턴 생성"""
    rates_path = Path(__file__).parent / 'data' / 'annual_rates.json'
    if not rates_path.exists():
        return []
    try:
        rates = json.loads(rates_path.read_text(encoding='utf-8'))
    except Exception:
        return []

    checks = []
    m = rates.get('medicare', {})
    current_year = rates.get('_meta', {}).get('year', rates.get('year', 2026))
    prev_year = current_year - 1

    # Part B deductible: 2025=$257, 2026=$283
    pb_deductible = m.get('part_b', {}).get('annual_deductible')
    if pb_deductible:
        # 이전 연도 알려진 값들
        stale_pb = [v for v in [257, 226, 203, 185] if v != pb_deductible]
        for old_val in stale_pb:
            checks.append((
                re.compile(rf'Part\s+B\b.{{0,60}}\$\s*{old_val}\b|\$\s*{old_val}\b.{{0,60}}Part\s+B\s+deductible', re.IGNORECASE),
                f'Stale Part B deductible ${old_val} detected — {current_year} correct value is ${pb_deductible}'
            ))

    # Part A deductible: 2025=$1676, 2026=$1736
    pa_deductible = m.get('part_a', {}).get('inpatient_hospital_deductible')
    if pa_deductible:
        stale_pa = [v for v in [1676, 1632, 1600, 1556] if v != pa_deductible]
        for old_val in stale_pa:
            checks.append((
                re.compile(rf'Part\s+A\b.{{0,80}}\$\s*{old_val:,}\b|\$\s*{old_val:,}\b.{{0,80}}Part\s+A\s+(?:hospital\s+)?deductible', re.IGNORECASE),
                f'Stale Part A deductible ${old_val:,} detected — {current_year} correct value is ${pa_deductible:,}'
            ))

    # ── IRA 기여 한도 (50세 이상) ─────────────────────────────────────────
    # 2022=$6,000 / 2023=$6,500 / 2024+=$7,000 (50+: $8,000)
    ira_section  = rates.get('ira_401k', {})
    ira_50plus   = ira_section.get('ira_contribution_50_plus')
    ira_under_50 = ira_section.get('ira_contribution_under_50')
    if ira_50plus:
        stale_ira_50 = [v for v in [7500, 7000, 6500, 6000, 5500] if v != ira_50plus]
        for old_val in stale_ira_50:
            checks.append((
                re.compile(
                    rf'\b(?:ira|roth\s+ira|traditional\s+ira)\b.{{0,80}}'
                    rf'\$\s*{old_val:,}\b',
                    re.IGNORECASE | re.DOTALL
                ),
                f'Stale IRA limit ${old_val:,} — {current_year}: under-50 ${ira_under_50:,} / 50+ ${ira_50plus:,}'
            ))

    # ── 401k 기여 한도 (50~59세 / 64세) ────────────────────────────────────
    # 2022=$27,000 / 2023=$30,000 / 2024=$30,500 / 2025=$31,000(50-59,64)
    contrib_50_59 = ira_section.get('401k_contribution_50_59_64')
    if contrib_50_59:
        stale_401k = [v for v in [30500, 30000, 27000, 26000, 25000] if v != contrib_50_59]
        for old_val in stale_401k:
            checks.append((
                re.compile(
                    rf'\b401[ck]\b.{{0,80}}\$\s*{old_val:,}\b',
                    re.IGNORECASE | re.DOTALL
                ),
                f'Stale 401k contribution ${old_val:,} — {current_year} limit is ${contrib_50_59:,} (age 50-59/64)'
            ))

    # ── Social Security COLA ─────────────────────────────────────────────────
    # 2024=3.2% / 2025=2.5% — "COLA of X%" 형태 오류 차단
    ss   = rates.get('social_security', {})
    cola = ss.get('cola_2026_percent') or ss.get(f'cola_{current_year}_percent')
    if cola:
        # 알려진 이전 COLA 값들 (잘못 쓰이면 차단)
        stale_cola = [v for v in [3.2, 8.7, 5.9, 1.3] if abs(v - cola) > 0.01]
        for old_val in stale_cola:
            checks.append((
                re.compile(
                    rf'\bcola\b.{{0,60}}{re.escape(str(old_val))}\s*%'
                    rf'|\b{re.escape(str(old_val))}\s*%\b.{{0,60}}cola\b',
                    re.IGNORECASE | re.DOTALL
                ),
                f'Stale COLA figure {old_val}% — {current_year} COLA is {cola}%'
            ))

    # ── Medicare Advantage OOP 상한 ───────────────────────────────────────────
    # 2025=$8,850 / 2026=$9,350 (in-network)
    adv = m.get('advantage', {})
    ma_oop = adv.get('max_oop_in_network')
    if ma_oop:
        stale_ma = [v for v in [8850, 8300, 7550] if v != ma_oop]
        for old_val in stale_ma:
            checks.append((
                re.compile(
                    rf'Medicare\s+Advantage\b.{{0,100}}\$\s*{old_val:,}\b'
                    rf'|\$\s*{old_val:,}\b.{{0,80}}(?:Medicare\s+Advantage|MA\s+plan)',
                    re.IGNORECASE | re.DOTALL
                ),
                f'Stale Medicare Advantage OOP cap ${old_val:,} — {current_year} in-network limit is ${ma_oop:,}'
            ))

    return checks

_STALE_FIGURE_CHECKS = _load_stale_figure_checks()


class PublishBlocked(Exception):
    """HARD_BLOCK 조건 위반 시 발생 — 발행 파이프라인 즉시 중단"""
    pass


def _word_count(html: str) -> int:
    text = BeautifulSoup(html, 'html.parser').get_text()
    return len(text.split())


# ─── 중복 제목 감지 ──────────────────────────────────────────────

_TITLE_LOG = _BASE_DIR / 'data' / 'published_titles.json'


def _title_ngrams(title: str, n: int = 2) -> set:
    """소문자 정규화 후 n-gram 집합 생성 (단어 단위, 기본 2-gram).
    2-gram이 3-gram보다 민감도가 높아 유사 제목을 더 잘 잡아냄."""
    words = re.sub(r'[^a-z0-9 ]', '', title.lower()).split()
    if len(words) < n:
        return set(words)
    return {' '.join(words[i:i+n]) for i in range(len(words) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_published_titles() -> list:
    if _TITLE_LOG.exists():
        with open(_TITLE_LOG, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_published_title(title: str) -> None:
    """발행 성공 후 auto_publish.py에서 호출"""
    try:
        titles = load_published_titles()
        titles.append({'title': title, 'saved_at': datetime.now().isoformat(timespec='seconds')})
        _TITLE_LOG.parent.mkdir(exist_ok=True)
        with open(_TITLE_LOG, 'w', encoding='utf-8') as f:
            json.dump(titles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f'[GOVERNOR] 제목 저장 실패: {e}')


def _check_duplicate_title(title: str, threshold: float = 0.6) -> None:
    """기존 발행 제목과 2-gram Jaccard 유사도 threshold 이상이면 예외 발생.
    과거엔 SOFT_WARN(경고만)이라 같은 주제가 재발행되는 걸 못 막았음 — HARD_BLOCK으로 전환."""
    published = load_published_titles()
    if not published:
        return
    new_ngrams = _title_ngrams(title)
    for entry in published:
        old_title   = entry.get('title', '')
        old_ngrams  = _title_ngrams(old_title)
        similarity  = _jaccard(new_ngrams, old_ngrams)
        if similarity >= threshold:
            raise PublishBlocked(
                f'[HARD] 유사 제목 감지 (유사도 {similarity:.0%}): "{old_title}" — 중복 주제 재생성 필요'
            )


def run(article: dict) -> dict:
    """
    발행 전 품질 검사 실행.

    Parameters
    ----------
    article : dict
        auto_publish.py 에서 조립한 article dict.
        필수 키: _html_content, title, meta, tags

    Returns
    -------
    dict
        {
          'blocked': False,
          'warnings': ['...', ...],
          'word_count': 1523,
          'hard_checks': ['PASS', ...],
        }

    Raises
    ------
    PublishBlocked
        HARD_BLOCK 조건 위반 시 즉시 예외 발생.
    """
    html     = article.get('_html_content', article.get('body', ''))
    title    = article.get('title', '')
    meta     = article.get('meta', '')
    tags     = article.get('tags', [])

    hard_checks = []
    warnings    = []

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 1 — 빈 제목 / 빈 HTML
    # ═══════════════════════════════════════════════════════
    if not title.strip():
        raise PublishBlocked('[HARD] 제목(title)이 비어 있음')
    if not html.strip():
        raise PublishBlocked('[HARD] HTML 본문(_html_content)이 비어 있음')
    hard_checks.append('TITLE_HTML: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 1.5 — 중복 제목 감지 (2-gram Jaccard 유사도)
    # ═══════════════════════════════════════════════════════
    _check_duplicate_title(title)
    hard_checks.append('DUPLICATE_TITLE: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 2 — 최소 단어수 (카테고리별)
    #   A/B : HARD 1,200 / SOFT 1,600  (YMYL: Medicare/Retirement — Google 신뢰도 기준 상향)
    #   C/D : HARD 1,000 / SOFT 1,400  (Aging in Place / Health)
    # ═══════════════════════════════════════════════════════
    category_key  = article.get('category_key', '').upper()
    _is_cd        = category_key in ('C', 'D')
    hard_min_wc   = 1000 if _is_cd else 1200
    soft_min_wc   = 1400 if _is_cd else 1600
    soft_range_lbl = '1,400-1,800' if _is_cd else '1,600-2,000'

    wc = _word_count(html)
    logger.info(f'[GOVERNOR] 단어수: {wc} (카테고리: {category_key or "unknown"})')
    if wc < hard_min_wc:
        raise PublishBlocked(
            f'[HARD] 단어수 {wc} < {hard_min_wc} (JSON 잘림 의심) — 재생성 필요'
        )
    hard_checks.append(f'MIN_WORDS({wc}): PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 3 — CJK 문자 감지
    # ═══════════════════════════════════════════════════════
    cjk_title = _CJK_RE.findall(title)
    cjk_html  = _CJK_RE.findall(html)
    if cjk_title or cjk_html:
        sample = ''.join((cjk_title + cjk_html)[:10])
        raise PublishBlocked(f'[HARD] CJK/비영어 문자 감지: "{sample}" — 재생성 필요')
    hard_checks.append('CJK: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 4 — BANNED_HARD 문구
    # ═══════════════════════════════════════════════════════
    text_lower = html.lower()
    hard_found = [p for p in BANNED_HARD if p in text_lower]
    if hard_found:
        raise PublishBlocked(f'[HARD] AI 특유 금지 문구 감지: {hard_found} — 재생성 필요')
    hard_checks.append('BANNED_HARD: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 5 — 사실 오류 패턴
    # ═══════════════════════════════════════════════════════
    # <hr> 이후는 면책문구 + Keep Reading 영역 — 팩트체크 대상 제외
    _soup_full = BeautifulSoup(html, 'html.parser')
    _hr = _soup_full.find('hr')
    _body_html = str(_hr.find_previous_siblings()) if _hr else html
    # 본문만 plain text 추출 (Keep Reading / 면책문구 제외)
    _body_soup = BeautifulSoup(html, 'html.parser')
    if _hr:
        for el in _hr.find_all_next():
            el.decompose()
        _hr.decompose()
    plain_text = _body_soup.get_text()
    for pattern, desc in _FACTUAL_ERROR_PATTERNS:
        m = pattern.search(plain_text)
        if m:
            raise PublishBlocked(
                f'[HARD] 사실 오류 패턴 감지: {desc} — 매칭된 문장: "{m.group(0)[:150]}"'
            )
    hard_checks.append('FACTUAL_ERRORS: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 6 — 개인참조 0회 정책
    # 프롬프트가 NO I-REFERENCE로 변경됨 (AdSense Helpful Content)
    # AI가 경험 있는 척 1인칭 서사 작성 = Google 신뢰도 패널티 위험
    # ═══════════════════════════════════════════════════════
    personal_hits = list(_PERSONAL_REF_RE.finditer(plain_text))
    if personal_hits:
        contexts = [
            plain_text[max(0, m.start() - 40):m.end() + 40].strip()
            for m in personal_hits[:3]
        ]
        raise PublishBlocked(
            f'[HARD] 개인참조 {len(personal_hits)}회 감지 (허용: 0회): '
            f'{[m.group(0) for m in personal_hits[:4]]} — 문맥: {contexts} '
            f'— AI 1인칭 서사 금지 (AdSense Helpful Content 정책)'
        )
    hard_checks.append('PERSONAL_REF(0): PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 7 — 연간 수치 stale 감지
    # annual_rates.json 기반 이전 연도 수치 사용 차단
    # ═══════════════════════════════════════════════════════
    for pattern, desc in _STALE_FIGURE_CHECKS:
        if pattern.search(plain_text):
            raise PublishBlocked(f'[HARD] 수치 오류: {desc}')
    hard_checks.append(f'STALE_FIGURES({len(_STALE_FIGURE_CHECKS)} checks): PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 8 — 공식 출처 링크 최소 2개 (E-E-A-T)
    # medicare.gov / ssa.gov / cms.gov 링크가 없으면 AdSense 심사 탈락
    # ═══════════════════════════════════════════════════════
    _OFFICIAL_DOMAINS = [
        # Medicare / Insurance / Social Security (A/B 카테고리)
        'medicare.gov', 'ssa.gov', 'cms.gov', 'shiphelp.org',
        # 건강·웰니스 공식 기관 (C/D 카테고리 — 그리프·탈수·운동·영양 등)
        'cdc.gov', 'nih.gov', 'nia.nih.gov', 'medlineplus.gov', 'acl.gov',
    ]
    official_links = [d for d in _OFFICIAL_DOMAINS if d in html.lower()]
    if len(official_links) < 1:
        raise PublishBlocked(
            '[HARD] 공식 출처 링크 없음 — medicare.gov / ssa.gov / cdc.gov / nih.gov 중 '
            '최소 1개 이상 본문에 삽입 필요 (AdSense E-E-A-T 요건)'
        )
    hard_checks.append(f'OFFICIAL_LINKS({len(official_links)}개): PASS')

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 1 — 목표 단어수 미달 (카테고리별)
    # ═══════════════════════════════════════════════════════
    if wc < soft_min_wc:
        msg = f'[SOFT] 단어수 {wc} < {soft_min_wc:,} (목표 범위 {soft_range_lbl}) — 발행은 되지만 확인 권장'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 2 — 제목 길이 (65자 권장)
    # ═══════════════════════════════════════════════════════
    if len(title) > 65:
        msg = f'[SOFT] 제목 {len(title)}자 > 65자 (SEO 권장 상한) — "{title[:70]}..."'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 3 — 메타 디스크립션 길이 (155자 권장)
    # ═══════════════════════════════════════════════════════
    if meta and len(meta) > 155:
        msg = f'[SOFT] 메타 디스크립션 {len(meta)}자 > 155자 (SEO 권장 상한)'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 4 — 태그 수 (Blogger API 8개 한도)
    # ═══════════════════════════════════════════════════════
    fixed_labels = article.get('_fixed_labels', [])
    ai_tags      = tags if isinstance(tags, list) else []
    # publisher_bot은 AI 태그 최대 4개 선택 + 고정 라벨 4개 = 최대 8개
    # 8개 초과 가능성 사전 경고
    projected = len(fixed_labels) + min(len(ai_tags), 4)
    if projected > 8:
        msg = f'[SOFT] 예상 라벨 수 {projected}개 > 8개 (Blogger API 한도) — publisher_bot이 자동 자름'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 5 — BANNED_SOFT 문구
    # ═══════════════════════════════════════════════════════
    soft_found = [p for p in BANNED_SOFT if p in text_lower]
    if soft_found:
        msg = f'[SOFT] 경고 문구 감지 (통과): {soft_found}'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # SOFT CHECK 6 — 더미 링크 (publisher_bot이 비활성 버튼으로 처리)
    # ═══════════════════════════════════════════════════════
    if 'example.com/pending' in html or 'example.com' in html:
        msg = '[SOFT] 더미 링크(example.com) 감지 — publisher_bot이 비활성 버튼으로 렌더링'
        logger.warning(msg)
        warnings.append(msg)

    # ═══════════════════════════════════════════════════════
    # 결과 요약
    # ═══════════════════════════════════════════════════════
    result = {
        'blocked':     False,
        'warnings':    warnings,
        'word_count':  wc,
        'hard_checks': hard_checks,
    }

    if warnings:
        logger.warning(f'[GOVERNOR] SOFT 경고 {len(warnings)}건 — 발행 진행')
    else:
        logger.info(f'[GOVERNOR] 모든 검사 통과 ({wc}단어) — 발행 진행')

    _log_result(title, result)
    return result


def _log_result(title: str, result: dict) -> None:
    """governor 실행 결과를 logs/governor.jsonl 에 누적 기록 (JSON Lines 형식)."""
    try:
        _LOG_DIR.mkdir(exist_ok=True)
        record = {
            'ts':         datetime.now().isoformat(timespec='seconds'),
            'title':      title,
            'word_count': result['word_count'],
            'hard_checks': result['hard_checks'],
            'warnings':   result['warnings'],
            'blocked':    result['blocked'],
        }
        with open(_GOV_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.warning(f'[GOVERNOR] 로그 기록 실패: {e}')


def save_draft(article: dict, reason: str) -> Path:
    """PublishBlocked 발생 시 article을 drafts/ 폴더에 저장.
    auto_publish.py 의 except PublishBlocked 블록에서 호출.

    Returns
    -------
    Path : 저장된 draft 파일 경로
    """
    _DRAFT_DIR.mkdir(exist_ok=True)
    ts    = datetime.now().strftime('%Y%m%d_%H%M%S')
    title = article.get('title', 'untitled')[:40]
    safe  = re.sub(r'[^\w\-]', '_', title)
    path  = _DRAFT_DIR / f'{ts}_{safe}.json'
    payload = {
        'saved_at':    datetime.now().isoformat(),
        'block_reason': reason,
        'article':     {k: v for k, v in article.items() if k != '_html_content'},
        'html_preview': (article.get('_html_content') or '')[:500],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f'[GOVERNOR] Draft 저장: {path.name}')
    return path
