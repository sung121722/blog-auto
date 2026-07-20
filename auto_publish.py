"""
Healthy After 50 — 자동 발행 메인 파이프라인
전략: Nostalgia Hook → High-Value Funnel (Medicare / Retirement / Aging in Place)
"""
import re
import sys
import logging
import requests
from pathlib import Path
from datetime import datetime

# .env 최우선 로드 (Task Scheduler / GitHub Actions 환경 대응)
_BASE = Path(__file__).parent
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE / 'bots'))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_BASE / '.env', override=True)

from bots import publisher_bot
from senior_generator import generate_post
from senior_collector import collect_keywords_for_today, mark_keyword_used, mark_hook_used, mark_opening_used
from senior_config import get_post_labels, UNSPLASH_ACCESS_KEY
import publish_governor
from publish_governor import PublishBlocked, save_published_title

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 이미지 (Unsplash URL — base64 아닌 직접 링크)
# ─────────────────────────────────────────

# ─── Unsplash API 실패 시 비상 이미지 풀 (카테고리별) ─────────────
# API 한도 초과 / 네트워크 오류 시 무조건 이 URL 중 하나 사용
EMERGENCY_IMAGES = {
    'A': [  # Medicare & Senior Living
        ('https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1559757175-5700dde675bc?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1773227060032-1bfb40b2b376?w=1080', 'Unsplash'),
    ],
    'B': [  # Retirement & Estate Planning
        ('https://images.unsplash.com/photo-1554224155-1696413565d3?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1514415008039-efa173293080?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1509594983248-0824814c1393?w=1080', 'Unsplash'),
    ],
    'C': [  # Aging in Place
        ('https://images.unsplash.com/photo-1651766231253-8bc86a2e1f9e?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1722764387572-ca8789420aa3?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1758686254218-30e3abffba4e?w=1080', 'Unsplash'),
    ],
    'D': [  # Senior Health & Wellness
        ('https://images.unsplash.com/photo-1505685679686-2490cab6217d?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1511256094521-c1cf19529095?w=1080', 'Unsplash'),
        ('https://images.unsplash.com/photo-1546383906-0c780bf53528?w=1080', 'Unsplash'),
    ],
}


def fetch_unsplash_url(query: str, category_key: str = None) -> tuple:
    """Unsplash 이미지 URL 반환 — 다큐멘터리 수식어 강화 + 비상 이미지 풀 최종 보장"""
    words = query.split()
    enriched = f"{query} candid documentary authentic everyday life"

    fallback_queries = [
        enriched,                                            # 1차: 수식어 강화
        query,                                               # 2차: 원본 쿼리
        ' '.join(words[:3]) if len(words) > 3 else None,   # 3차: 앞 3단어
        'cozy living room warm morning coffee light',        # 4차: 감성 풍경
        'nature trail peaceful morning sunlight',            # 5차: 자연 풍경
    ]

    if UNSPLASH_ACCESS_KEY:
        for q in fallback_queries:
            if not q:
                continue
            try:
                resp = requests.get(
                    'https://api.unsplash.com/photos/random',
                    params={'query': q, 'orientation': 'landscape', 'content_filter': 'high'},
                    headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info(f'Unsplash 이미지 (쿼리: "{q}")')
                return data['urls']['regular'], data['user']['name']
            except Exception as e:
                logger.warning(f'Unsplash 실패 (쿼리: "{q}"): {e}')

    # 최종 보장: 비상 이미지 풀에서 랜덤 선택 (API 없이도 항상 이미지 보장)
    import random as _random
    pool = EMERGENCY_IMAGES.get(category_key) or EMERGENCY_IMAGES['B']
    img_url, credit = _random.choice(pool)
    logger.warning(f'[EMERGENCY IMAGE] Unsplash API 실패 → 비상 이미지 사용 (카테고리: {category_key})')
    return img_url, credit


def build_image_html(img_url: str, photographer: str, alt_text: str) -> str:
    if not img_url:
        return ''
    return (
        f'<figure style="margin:0 0 24px;">'
        f'<img src="{img_url}" alt="{alt_text}" style="width:100%;border-radius:8px;" />'
        f'<figcaption style="font-size:0.75em;color:#888;text-align:right;">'
        f'Photo by {photographer} on '
        f'<a href="https://unsplash.com" target="_blank" rel="noopener">Unsplash</a>'
        f'</figcaption></figure>'
    )


# ─────────────────────────────────────────
# slug 생성
# ─────────────────────────────────────────

def make_slug(title: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return slug or datetime.now().strftime('post-%Y%m%d-%H%M%S')


# ─────────────────────────────────────────
# 메인 파이프라인
# ─────────────────────────────────────────

def _is_duplicate_keyword(keyword: str, published_titles: list, threshold: float = 0.5) -> bool:
    """키워드가 기존 발행 제목과 너무 유사하면 True — 생성 전 API 호출 낭비 예방.
    (제목은 primary_keyword를 그대로 반영해 짓도록 지시하므로 키워드 단위 비교로도 유효)"""
    kw_ngrams = publish_governor._title_ngrams(keyword)
    for entry in published_titles:
        old_ngrams = publish_governor._title_ngrams(entry.get('title', ''))
        if publish_governor._jaccard(kw_ngrams, old_ngrams) >= threshold:
            return True
    return False


def _pick_nonduplicate_keywords(category_key: str | None, max_attempts: int = 5) -> dict:
    """중복 발행 제목과 겹치지 않는 키워드 세트를 뽑을 때까지 재시도 (API 호출 없이 사전 필터링)."""
    published_titles = publish_governor.load_published_titles()
    excluded: set = set()
    collected = collect_keywords_for_today(category_key=category_key)

    for attempt in range(1, max_attempts + 1):
        if not _is_duplicate_keyword(collected['primary_keyword'], published_titles):
            return collected
        logger.warning(
            f'[사전필터] 키워드가 기존 발행 제목과 유사 — 재선택 (시도 {attempt}/{max_attempts}): '
            f'"{collected["primary_keyword"]}"'
        )
        excluded.add(collected['primary_keyword'])
        collected = collect_keywords_for_today(
            category_key=collected['category_key'], exclude_primary=excluded
        )

    logger.warning('[사전필터] 중복 없는 키워드를 못 찾음 — 마지막 후보로 진행')
    return collected


def run():
    logger.info('=' * 55)
    logger.info('  Healthy After 50 — Pipeline Start')
    logger.info('=' * 55)

    MAX_RETRIES = 2
    category_key_locked = None  # 재시도 시 같은 카테고리 유지
    tried_keywords: set = set()
    result = None

    for attempt in range(1, MAX_RETRIES + 1):
        # 1. 키워드 수집 — 기존 발행 제목과 겹치지 않는 키워드로 사전 필터링
        collected = _pick_nonduplicate_keywords(category_key_locked)
        category_key = collected['category_key']
        category_info = collected['category_info']
        category_key_locked = category_key
        tried_keywords.add(collected['primary_keyword'])

        logger.info(f'카테고리: {category_key} / {category_info["name"]} (시도 {attempt}/{MAX_RETRIES})')
        logger.info(f'Primary Keyword: {collected["primary_keyword"]}')

        # 2. 콘텐츠 생성 — collector가 선택한 키워드 직접 전달 (이력 우회 방지)
        logger.info('글 생성 중...')
        try:
            post = generate_post(
                category_key=category_key,
                primary_keyword=collected['primary_keyword'],
                supporting_keywords=collected['supporting_keywords'],
            )
        except RuntimeError as e:
            logger.error(f'[생성 실패] {e}')
            if attempt < MAX_RETRIES:
                logger.warning(f'[생성 실패] 시도 {attempt + 1}회차로 재시도 (다른 키워드)')
            continue

        result = _publish_generated_post(post, category_key, category_info, collected)
        # result: True=발행 성공 / False=Blogger 발행 실패 or 수동검토 대기 / None=Governor 차단
        # False도 None과 동일하게 재시도 대상 — 예전엔 result is not None만 봐서
        # False(예: 중복 제목으로 Blogger가 거부)를 "완료"로 착각하고 재시도 없이 조용히 끝났음
        if result:
            break
        if attempt < MAX_RETRIES:
            logger.warning(f'[재시도] 시도 {attempt + 1}회차로 재시도 (다른 키워드) — 이전 결과: {result}')

    if not result:
        logger.error(f'{MAX_RETRIES}회 모두 발행 실패 — 오늘은 발행 없이 종료')
        try:
            publisher_bot.send_telegram(
                f'🚫 {MAX_RETRIES}회 재시도 후 발행 실패 — 오늘은 초안 없이 종료\n'
                f'시도한 키워드: {", ".join(tried_keywords)}'
            )
        except Exception:
            pass
        return

    logger.info('=' * 55)
    return result


def _publish_generated_post(post: dict, category_key: str, category_info: dict, collected: dict):
    """생성된 post를 이미지/HTML 조립 후 Governor 검사·발행. Governor 차단 시 None 반환(재시도 유도)."""
    # 3. 이미지 수집 (URL 방식) — 항상 이미지 보장 (비상 풀 최종 백업)
    logger.info('이미지 가져오는 중...')
    image_query = post.get('image_query', 'older adult at home natural morning light')
    img_url, photographer = fetch_unsplash_url(image_query, category_key=category_key)
    image_html = build_image_html(img_url, photographer, post.get('title', ''))
    logger.info(f'이미지 준비: {img_url[:70]}...')

    # 4. HTML 조립 (이미지 + 본문)
    full_html = image_html + post['html_content']

    # 5. publisher_bot용 article dict 구성
    tags = post.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    # 고정 카테고리 라벨 (4개) + AI 태그 분리 보관
    fixed_labels = get_post_labels(category_key)

    article = {
        'title':          post['title'],
        'meta':           post.get('meta_description', ''),
        'slug':           make_slug(post['title']),
        'tags':           tags,                   # AI 생성 태그만 (publisher_bot이 최대 4개 선택)
        '_fixed_labels':  fixed_labels,           # 고정 카테고리 라벨 (publisher_bot이 추가)
        'corner':         category_info['name'],
        'category_key':   category_key,           # A/B/C/D — 내부링크 카테고리 매칭용
        'body':           re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', full_html)).strip(),  # 안전장치 키워드 검사용 순수 텍스트
        '_html_content':  full_html,              # publisher_bot이 이걸 우선 사용
        '_img_url':       img_url,                # Blogger 썸네일 등록용 (None이면 생략)
        'quality_score':  80,                     # 아래 Governor 통과 후 실제 값으로 갱신됨
        'sources':        [],
        'disclaimer':     '',
    }

    # 6. 품질 게이트 (publish_governor)
    logger.info('[GOVERNOR] 품질 검사 시작...')
    try:
        gov_result = publish_governor.run(article)
        logger.info(f'[GOVERNOR] 통과 — {gov_result["word_count"]}단어, 경고 {len(gov_result["warnings"])}건')
    except PublishBlocked as e:
        draft_path = publish_governor.save_draft(article, str(e))
        logger.error(f'[GOVERNOR] 발행 차단: {e}')
        logger.error(f'[GOVERNOR] Draft 저장 완료: {draft_path}')
        return None  # 상위 run()의 재시도 루프로 신호 전달

    # Governor 경고 개수 기반 실제 품질 점수 (안전장치 min_quality_score_for_auto가 실효성을 갖도록)
    article['quality_score'] = max(50, 100 - len(gov_result['warnings']) * 10)

    # 7. Blogger 발행
    logger.info(f'발행 중: {post["title"]}')
    result = publisher_bot.publish(article)

    if result:
        logger.info('발행 성공!')
        mark_keyword_used(post['primary_keyword'], category_key)
        # Hook 앵글 이력 기록 (30일 쿨다운)
        hook_info = post.get('_hook', {})
        if hook_info.get('hook_angle'):
            mark_hook_used(hook_info['hook_angle'], hook_info.get('hook_type', ''), category_key)
        # 중복 방지용 제목 이력 기록
        save_published_title(post['title'])
        # 오프닝 문장 이력 기록 (다음 글 생성 시 반복 방지용)
        opening_text = re.sub(r'<[^>]+>', ' ', post.get('html_content', ''))
        opening_text = re.sub(r'\s+', ' ', opening_text).strip()[:200]
        if opening_text:
            mark_opening_used(opening_text)
    else:
        logger.warning('발행 실패 또는 검토 대기')

    return result


if __name__ == '__main__':
    run()
