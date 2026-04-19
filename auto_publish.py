"""
Today's Senior TV — 자동 발행 메인 파이프라인
전략: Nostalgia Hook → High-Value Funnel (Medicare / Retirement / Aging in Place)
"""
import re
import sys
import logging
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'bots'))

from bots import publisher_bot
from senior_generator import generate_post
from senior_collector import collect_keywords_for_today, mark_keyword_used
from senior_config import get_post_labels, UNSPLASH_ACCESS_KEY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 이미지 (Unsplash URL — base64 아닌 직접 링크)
# ─────────────────────────────────────────

def fetch_unsplash_url(query: str) -> tuple:
    """Unsplash에서 이미지 URL 반환 (다운로드 없이 직접 링크 사용)"""
    if not UNSPLASH_ACCESS_KEY:
        return None, None
    try:
        resp = requests.get(
            'https://api.unsplash.com/photos/random',
            params={'query': query, 'orientation': 'landscape', 'content_filter': 'high'},
            headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data['urls']['regular'], data['user']['name']
    except Exception as e:
        logger.warning(f'Unsplash 실패: {e}')
        return None, None


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

    # 3. 이미지 수집 (URL 방식)
    logger.info('이미지 가져오는 중...')
    image_query = post.get('image_query', 'vintage americana seniors nostalgia')
    img_url, photographer = fetch_unsplash_url(image_query)
    image_html = build_image_html(img_url, photographer, post.get('title', ''))
    if img_url:
        logger.info(f'이미지 준비: {img_url[:60]}...')
    else:
        logger.warning('이미지 없이 발행 진행')

    # 4. HTML 조립 (이미지 + 본문)
    full_html = image_html + post['html_content']

    # 5. publisher_bot용 article dict 구성
    tags = post.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    # 카테고리 라벨 추가
    labels = get_post_labels(category_key)
    all_tags = list(set(tags + labels))

    article = {
        'title':         post['title'],
        'meta':          post.get('meta_description', ''),
        'slug':          make_slug(post['title']),
        'tags':          all_tags,
        'corner':        category_info['name'],
        'body':          '',           # HTML 직접 사용
        '_html_content': full_html,    # publisher_bot이 이걸 우선 사용
        'quality_score': 80,           # 안전장치 통과
        'sources':       [],
        'disclaimer':    '',
    }

    # 6. Blogger 발행
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
