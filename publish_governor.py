"""
publish_governor.py — 발행 전 최종 품질 게이트

파이프라인 위치:
  generate_post() → [publish_governor] → publisher_bot.publish()

두 계층으로 나뉨:
  HARD_BLOCK : 발행 즉시 차단 → PublishBlocked 예외 발생
  SOFT_WARN  : 경고 로그 기록 + 통과 (수동 확인 권장)

HARD_BLOCK 조건:
  1. 최소 단어수 미달 (900) — JSON 잘림 감지
  2. CJK / 비ASCII 문자 — 한중일 문자 혼입
  3. BANNED_HARD 문구 — 순수 AI 특유 표현
  4. 사실 오류 패턴 — RMD 나이 오류, 잘못된 법률 연도 등
  5. 빈 제목 / 빈 HTML

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

    # ── 6. 가짜 연구 인용 (Hallucinated Citation) ────────────────
    # AI가 기관명 + 연도 + 구체적 % 수치를 조합해 없는 연구를 만들어내는 패턴 차단
    # BAD: "A 2025 study from Johns Hopkins found that X% fewer..."
    # BAD: "According to a 2026 Harvard report, seniors who... had 43%..."
    # OK:  "Research suggests tai chi reduces fall risk."
    # OK:  "Studies show regular exercise lowers heart disease risk."
    (
        re.compile(
            r'\b(?:a |an )?20\d{2}\s+(?:study|report|research|trial)\s+'
            r'(?:from|by|at|conducted by)\s+'
            r'(?:johns?\s+hopkins?|harvard|mayo\s+clinic|stanford|cdc|nih|aarp|'
            r'university\s+of|american\s+(?:heart|college|medical))\b',
            re.IGNORECASE | re.DOTALL
        ),
        'Fabricated citation detected: specific year + institution + study — '
        'use "research suggests" or "studies show" unless source is in research_context'
    ),

    # ── 7. 개인참조 2회 초과 (Personal Reference > 1) ────────────
    # 규칙: 글 당 정확히 1회만 허용 ("I watched a colleague..." 수준).
    # BAD: "I watched..." + "In one case I saw..." (2회)
    # OK:  "I watched a colleague once..." (1회만, 이후 I/my/I've 없음)
    # 감지: \b(i watched|i saw|i know|i once|i always|i remember|i tried|
    #            i learned|i've|i retired|when i|i helped|i've sat)\b
    # 2회 이상이면 HARD BLOCK
]

# 별도 처리 — 개인참조 횟수 감지 (패턴 리스트와 분리)
_PERSONAL_REF_RE = re.compile(
    r'\b(i\s+watched|i\s+saw|i\s+know|i\s+once|i\s+always|i\s+remember'
    r'|i\s+tried|i\s+learned|i\'ve|i\s+retired|when\s+i\s|i\s+helped'
    r'|i\'ve\s+sat|i\s+spent|i\s+worked|i\s+have\s+seen|i\s+have\s+watched'
    r'|i\s+can\'t|i\s+cannot|i\s+would|i\s+will|i\s+think|i\s+believe'
    r'|i\s+suggest|i\s+recommend)\b',
    re.IGNORECASE
)


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
    """기존 발행 제목과 Jaccard 유사도 0.6 이상이면 SOFT_WARN 반환."""
    published = load_published_titles()
    if not published:
        return None
    new_ngrams = _title_ngrams(title)
    for entry in published:
        old_title   = entry.get('title', '')
        old_ngrams  = _title_ngrams(old_title)
        similarity  = _jaccard(new_ngrams, old_ngrams)
        if similarity >= threshold:
            return f'[SOFT] 유사 제목 감지 (유사도 {similarity:.0%}): "{old_title}"'
    return None


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
    # HARD CHECK 2 — 최소 단어수 (카테고리별)
    #   A/B : HARD 900 / SOFT 1,400
    #   C/D : HARD 750 / SOFT 1,100
    # ═══════════════════════════════════════════════════════
    category_key  = article.get('category_key', '').upper()
    _is_cd        = category_key in ('C', 'D')
    hard_min_wc   = 750  if _is_cd else 900
    soft_min_wc   = 1100 if _is_cd else 1400
    soft_range_lbl = '1,100-1,400' if _is_cd else '1,400-1,800'

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
    plain_text = BeautifulSoup(html, 'html.parser').get_text()
    for pattern, desc in _FACTUAL_ERROR_PATTERNS:
        if pattern.search(plain_text):
            raise PublishBlocked(f'[HARD] 사실 오류 패턴 감지: {desc}')
    hard_checks.append('FACTUAL_ERRORS: PASS')

    # ═══════════════════════════════════════════════════════
    # HARD CHECK 6 — 개인참조 횟수 (정확히 1회만 허용)
    # "I watched", "I saw", "I tried" 등 1인칭 서사 표현
    # 2회 이상이면 독자 신뢰도 / YMYL 정책 위반
    # ═══════════════════════════════════════════════════════
    personal_matches = _PERSONAL_REF_RE.findall(plain_text)
    if len(personal_matches) > 1:
        raise PublishBlocked(
            f'[HARD] 개인참조 {len(personal_matches)}회 감지 (허용: 1회): '
            f'{personal_matches[:4]} — 프롬프트 PERSONAL REFERENCE 규칙 위반'
        )
    hard_checks.append(f'PERSONAL_REF({len(personal_matches)}): PASS')

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
    # SOFT CHECK 7 — 중복 제목 감지 (3-gram Jaccard 유사도)
    # ═══════════════════════════════════════════════════════
    dup_msg = _check_duplicate_title(title)
    if dup_msg:
        logger.warning(dup_msg)
        warnings.append(dup_msg)

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
