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
from senior_collector import collect_keywords_for_today, mark_keyword_used
from senior_config import get_post_labels, UNSPLASH_ACCESS_KEY
import publish_governor
from publish_governor import PublishBlocked

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

def run():
    logger.info('=' * 55)
    logger.info('  Today\'s Senior TV — Pipeline Start')
    logger.info('=' * 55)

    # 1. 키워드 수집
    collected = collect_keywords_for_today()
    category_key = collected['category_key']
    category_info = collected['category_info']

    logger.info(f'카테고리: {category_key} / {category_info["name"]}')
    logger.info(f'Primary Keyword: {collected["primary_keyword"]}')

    # 2. 콘텐츠 생성
    logger.info('글 생성 중...')
    post = generate_post(category_key=category_key)

    # 3. 이미지 수집 (URL 방식) — 항상 이미지 보장 (비상 풀 최종 백업)
    logger.info('이미지 가져오는 중...')
    image_query = post.get('image_query', 'vintage americana seniors nostalgia')
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
        'body':           '',                     # HTML 직접 사용
        '_html_content':  full_html,              # publisher_bot이 이걸 우선 사용
        '_img_url':       img_url,                # Blogger 썸네일 등록용 (None이면 생략)
        'quality_score':  80,                     # 안전장치 통과
        'sources':        [],
        'disclaimer':     '',
    }

    # 6. 품질 게이트 (publish_governor)
    logger.info('[GOVERNOR] 품질 검사 시작...')
    try:
        gov_result = publish_governor.run(article)
        logger.info(f'[GOVERNOR] 통과 — {gov_result["word_count"]}단어, 경고 {len(gov_result["warnings"])}건')
    except PublishBlocked as e:
        logger.error(f'[GOVERNOR] 발행 차단: {e}')
        raise

    # 7. Blogger 발행
    logger.info(f'발행 중: {post["title"]}')
    result = publisher_bot.publish(article)

    if result:
        logger.info('발행 성공!')
        mark_keyword_used(post['primary_keyword'], category_key)
    else:
        logger.warning('발행 실패 또는 검토 대기')

    logger.info('=' * 55)
    return result


if __name__ == '__main__':
    run()
