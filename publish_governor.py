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

import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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
# 패턴: 처방적 문맥에서 RMD 나이를 72로 언급 (역사적 서술 제외)
# OK:   "shifted from 72 to 73" / "under the old rules at 72"
# BAD:  "RMD begins at age 72" / "start RMDs at 72" / "RMD age is 72"
_FACTUAL_ERROR_PATTERNS = [
    (
        # "RMD begins/starts at age 72" / "RMD age is 72"
        re.compile(
            r'\b(?:rmd|required minimum distribution)s?\b.{0,80}'
            r'\b(?:begins?|starts?|age is|starts? at)\b.{0,30}\b72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD age stated as 72 (SECURE 2.0 changed it to 73 in 2023)'
    ),
    (
        # "start/begin RMDs at age 72" / "take your RMD at age 72"
        re.compile(
            r'\b(?:start|begin|take|taking)\b.{0,30}'
            r'\b(?:rmd|required minimum distribution)s?\b.{0,30}'
            r'\bat age 72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD age stated as 72 (correct age is 73 under SECURE 2.0)'
    ),
    (
        # "must start RMDs at 72" / "required to start at 72"
        re.compile(
            r'\b(?:must|required to|have to|need to)\b.{0,30}'
            r'\b(?:start|begin|take)\b.{0,30}'
            r'\b(?:rmd|required minimum distribution)s?\b.{0,30}\b72\b',
            re.IGNORECASE | re.DOTALL
        ),
        'RMD start requirement stated as age 72 (correct age is 73 under SECURE 2.0)'
    ),
]


class PublishBlocked(Exception):
    """HARD_BLOCK 조건 위반 시 발생 — 발행 파이프라인 즉시 중단"""
    pass


def _word_count(html: str) -> int:
    text = BeautifulSoup(html, 'html.parser').get_text()
    return len(text.split())


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
    # HARD CHECK 2 — 최소 단어수 (900)
    # ═══════════════════════════════════════════════════════
    wc = _word_count(html)
    logger.info(f'[GOVERNOR] 단어수: {wc}')
    if wc < 900:
        raise PublishBlocked(
            f'[HARD] 단어수 {wc} < 900 (JSON 잘림 의심) — 재생성 필요'
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
    # SOFT CHECK 1 — 목표 단어수 미달 (1,400)
    # ═══════════════════════════════════════════════════════
    if wc < 1400:
        msg = f'[SOFT] 단어수 {wc} < 1,400 (목표 범위 1,400-1,800) — 발행은 되지만 확인 권장'
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

    return result
