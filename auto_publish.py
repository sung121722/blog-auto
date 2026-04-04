"""
시니어 추억여행 자동 발행 스크립트
월·수·금 오전 6시 / 화·목·토 오전 5시 30분 자동 발행
"""
import sys
import json
import random
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from bots import writer_bot, publisher_bot, image_bot

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

DNA_PATH = Path('config/creative_dna.json')
DRAFTS_DIR = Path('data/drafts')
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)


def pick_random_topic():
    with open(DNA_PATH, encoding='utf-8') as f:
        dna = json.load(f)
    topics = dna.get('topic_pool', [])
    item = random.choice(topics)
    if isinstance(item, dict):
        return item.get('topic', str(item))
    return item


def insert_image_to_body(body: str, image_path: str) -> str:
    """본문 첫 번째 단락 뒤에 이미지 + 출처 표기 삽입"""
    try:
        import base64, json as _json
        img_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        ext = Path(image_path).suffix.lstrip('.')

        # 출처 정보 읽기 (Openverse 이미지인 경우)
        attr_path = Path(image_path).with_suffix('.attribution.json')
        attribution_html = ''
        if attr_path.exists():
            attr = _json.loads(attr_path.read_text(encoding='utf-8'))
            creator = attr.get('creator', '')
            creator_url = attr.get('creator_url', '')
            license_name = attr.get('license', '').upper()
            license_url = attr.get('license_url', '')
            source_url = attr.get('source', '')
            parts = []
            if creator and creator_url:
                parts.append(f'Photo by <a href="{creator_url}" target="_blank" rel="noopener">{creator}</a>')
            elif creator:
                parts.append(f'Photo by {creator}')
            if source_url:
                parts.append(f'via <a href="{source_url}" target="_blank" rel="noopener">Flickr/Wikimedia</a>')
            if license_name and license_url:
                parts.append(f'Licensed under <a href="{license_url}" target="_blank" rel="noopener">{license_name}</a>')
            if parts:
                attribution_html = f'<p style="text-align:center;font-size:12px;color:#888;margin-top:4px;">{" · ".join(parts)}</p>'

        img_tag = (
            f'<div style="text-align:center;margin:20px 0;">'
            f'<img src="data:image/{ext};base64,{b64}" style="max-width:100%;border-radius:8px;" />'
            f'{attribution_html}'
            f'</div>'
        )
        if '</p>' in body:
            idx = body.index('</p>') + 4
            return body[:idx] + '\n' + img_tag + '\n' + body[idx:]
        return img_tag + '\n' + body
    except Exception as e:
        logger.warning(f"이미지 삽입 실패: {e}")
        return body


def run():
    topic = pick_random_topic()
    logger.info(f"선택된 주제: {topic}")

    topic_data = {
        'topic': topic,
        'keywords': ['nostalgia', 'baby boomer', 'memories', '1960s', '1970s', 'vintage america'],
        'category': 'American Nostalgia'
    }

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = DRAFTS_DIR / f"senior_{timestamp}.json"

    logger.info("글 작성 중...")
    article = writer_bot.write_article(topic_data, out_path)
    if not article:
        logger.error("글 작성 실패")
        return False

    # Unsplash 이미지 가져오기
    logger.info("이미지 가져오는 중...")
    image_path = image_bot.fetch_unsplash_image(topic)
    if image_path:
        logger.info(f"이미지 준비: {image_path}")
        article['body'] = insert_image_to_body(article.get('body', ''), image_path)
    else:
        logger.warning("이미지 없이 발행 진행")

    logger.info("Blogger 발행 중...")
    result = publisher_bot.publish(article)
    if result:
        logger.info("발행 성공!")
    else:
        logger.warning("발행 실패 또는 검토 대기")
    return result


if __name__ == '__main__':
    run()
