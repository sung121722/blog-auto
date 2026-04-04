"""
이미지봇 (image_bot.py)
역할: 만평 코너용 이미지 생성/관리

IMAGE_MODE 환경변수로 모드 선택:

  manual  (기본) — 한컷 글 발행 시점에 프롬프트 1개를 Telegram으로 전송.
                   사용자가 직접 생성 후 data/images/ 에 파일 저장.

  request        — 스케줄러가 주기적으로 대기 중인 프롬프트 목록을 Telegram 전송.
                   사용자가 생성형 AI로 이미지 제작 후 Telegram으로 이미지 전송하면 자동 저장.
                   /images 명령으로 대기 목록 확인, /imgpick [번호]로 선택.

  auto           — OpenAI Images API (dall-e-3) 직접 호출. OPENAI_API_KEY 필요.
                   비용: 이미지당 $0.04-0.08 (ChatGPT Pro 구독과 별도).
"""
import json
import logging
import os
import random
import re
import uuid
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
IMAGES_DIR = DATA_DIR / 'images'
LOG_DIR = BASE_DIR / 'logs'
PENDING_PROMPTS_FILE = IMAGES_DIR / 'pending_prompts.json'

LOG_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'image_bot.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY', '')
PEXELS_API_KEY = os.getenv('PEXELS_API_KEY', '')
IMAGE_MODE = os.getenv('IMAGE_MODE', 'pexels').lower()  # manual | request | auto | unsplash | pexels


# ─── Telegram 전송 ────────────────────────────────────

def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram 설정 없음")
        print(text)
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    try:
        requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML',
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram 전송 실패: {e}")


# ─── 프롬프트 생성 ────────────────────────────────────

def build_cartoon_prompt(topic: str, description: str = '') -> str:
    """만평 스타일 이미지 프롬프트 생성 (범용 — 어떤 생성형 AI에도 사용 가능)"""
    desc_part = f" {description}" if description else ""
    prompt = (
        f"Korean editorial cartoon style, single panel.{desc_part} "
        f"Topic: {topic}. "
        f"Style: simple line art, expressive characters, thought-provoking social commentary, "
        f"Korean newspaper cartoon aesthetic, minimal color, black and white with accent colors. "
        f"No text in the image. Square format 1:1."
    )
    return prompt


# ─── 대기 프롬프트 관리 ───────────────────────────────

def load_pending_prompts() -> list[dict]:
    """pending_prompts.json 로드"""
    if not PENDING_PROMPTS_FILE.exists():
        return []
    try:
        return json.loads(PENDING_PROMPTS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_pending_prompts(prompts: list[dict]):
    """pending_prompts.json 저장"""
    PENDING_PROMPTS_FILE.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding='utf-8'
    )


def add_pending_prompt(topic: str, description: str, article_ref: str = '') -> dict:
    """새 프롬프트 대기 목록에 추가. 생성된 항목 반환."""
    prompts = load_pending_prompts()
    # 같은 주제가 이미 있으면 추가하지 않음
    for p in prompts:
        if p['topic'] == topic and p['status'] == 'pending':
            logger.info(f"이미 대기 중인 프롬프트: {topic}")
            return p

    prompt_text = build_cartoon_prompt(topic, description)
    item = {
        'id': str(len(prompts) + 1),  # 사람이 읽기 쉬운 번호
        'uid': uuid.uuid4().hex[:8],
        'topic': topic,
        'description': description,
        'prompt': prompt_text,
        'article_ref': article_ref,
        'status': 'pending',  # pending | selected | done
        'created_at': datetime.now().isoformat(),
        'image_path': '',
    }
    prompts.append(item)
    save_pending_prompts(prompts)
    logger.info(f"프롬프트 추가 #{item['id']}: {topic}")
    return item


def get_pending_prompts(status: str = 'pending') -> list[dict]:
    """상태별 프롬프트 목록"""
    return [p for p in load_pending_prompts() if p['status'] == status]


def mark_prompt_selected(prompt_id: str) -> dict | None:
    """사용자가 선택한 프롬프트를 selected 상태로 변경"""
    prompts = load_pending_prompts()
    for p in prompts:
        if p['id'] == str(prompt_id):
            p['status'] = 'selected'
            p['selected_at'] = datetime.now().isoformat()
            save_pending_prompts(prompts)
            return p
    return None


def mark_prompt_done(prompt_id: str, image_path: str) -> dict | None:
    """이미지 수령 완료 처리"""
    prompts = load_pending_prompts()
    for p in prompts:
        if p['id'] == str(prompt_id):
            p['status'] = 'done'
            p['image_path'] = image_path
            p['done_at'] = datetime.now().isoformat()
            save_pending_prompts(prompts)
            logger.info(f"프롬프트 #{prompt_id} 완료: {image_path}")
            return p
    return None


def get_prompt_by_id(prompt_id: str) -> dict | None:
    for p in load_pending_prompts():
        if p['id'] == str(prompt_id):
            return p
    return None


# ─── 이미지 수신 저장 ─────────────────────────────────

def save_image_from_bytes(image_bytes: bytes, topic: str, prompt_id: str) -> str:
    """bytes로 받은 이미지를 data/images/ 에 저장. 경로 반환."""
    safe_name = re.sub(r'[^\w가-힣-]', '_', topic)[:50]
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_p{prompt_id}_{safe_name}.png"
    save_path = IMAGES_DIR / filename
    save_path.write_bytes(image_bytes)
    logger.info(f"이미지 저장: {save_path}")
    return str(save_path)


def save_image_from_telegram(file_bytes: bytes, prompt_id: str) -> str | None:
    """Telegram으로 받은 이미지 저장 및 프롬프트 완료 처리"""
    prompt = get_prompt_by_id(prompt_id)
    if not prompt:
        logger.warning(f"프롬프트 #{prompt_id} 없음")
        return None

    image_path = save_image_from_bytes(file_bytes, prompt['topic'], prompt_id)
    mark_prompt_done(prompt_id, image_path)
    return image_path


# ─── request 모드 — 배치 전송 ──────────────────────────

def send_prompt_batch():
    """
    request 모드 주기 실행.
    data/topics/ 에서 한컷 코너 글감을 스캔해 프롬프트 대기 목록에 추가하고
    현재 pending 상태인 프롬프트 전체를 Telegram으로 전송.
    """
    logger.info("=== 이미지 프롬프트 배치 전송 시작 ===")

    # 한컷 글감 스캔 → 대기 목록에 추가
    topics_dir = DATA_DIR / 'topics'
    for f in sorted(topics_dir.glob('*.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            if data.get('corner') == '한컷':
                add_pending_prompt(
                    topic=data.get('topic', ''),
                    description=data.get('description', ''),
                    article_ref=str(f),
                )
        except Exception:
            pass

    pending = get_pending_prompts('pending')
    selected = get_pending_prompts('selected')
    active = pending + selected

    if not active:
        send_telegram("🎨 현재 이미지 제작 요청이 없습니다.")
        logger.info("대기 프롬프트 없음")
        return

    lines = [
        f"🎨 <b>[이미지 제작 요청 — {len(active)}건]</b>\n",
        "아래 목록에서 제작하실 항목을 선택해주세요.\n",
        f"/imgpick [번호] 로 선택 → 생성형 AI(Midjourney, DALL-E, Stable Diffusion 등)로 제작 → "
        f"이미지를 이 채팅에 전송해주세요.\n",
    ]
    for item in active:
        status_icon = '🔄' if item['status'] == 'selected' else '⏳'
        lines.append(
            f"{status_icon} <b>#{item['id']}</b> {item['topic']}\n"
            f"   📝 <code>{item['prompt'][:200]}...</code>\n"
        )
    lines.append("\n/images — 전체 목록 재확인")

    send_telegram('\n'.join(lines))
    logger.info(f"배치 전송 완료: {len(active)}건")


def send_single_prompt(prompt_id: str):
    """특정 프롬프트 1개를 전체 내용으로 Telegram 전송"""
    prompt = get_prompt_by_id(prompt_id)
    if not prompt:
        send_telegram(f"❌ #{prompt_id} 번 프롬프트를 찾을 수 없습니다.")
        return

    mark_prompt_selected(prompt_id)
    msg = (
        f"🎨 <b>[이미지 제작 — #{prompt['id']}]</b>\n\n"
        f"📌 주제: <b>{prompt['topic']}</b>\n\n"
        f"📝 프롬프트 (복사해서 생성형 AI에 붙여넣으세요):\n\n"
        f"<code>{prompt['prompt']}</code>\n\n"
        f"✅ 이미지 완성 후 <b>이 채팅에 이미지를 전송</b>하면 자동으로 저장됩니다.\n"
        f"(전송 시 캡션에 <code>#{prompt['id']}</code> 를 입력해주세요)"
    )
    send_telegram(msg)
    logger.info(f"단일 프롬프트 전송 #{prompt_id}: {prompt['topic']}")


# ─── auto 모드 ────────────────────────────────────────

def generate_image_auto(prompt: str, topic: str) -> str | None:
    """OpenAI DALL-E 3 API로 이미지 자동 생성"""
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY 없음 — 자동 이미지 생성 불가")
        return None
    try:
        resp = requests.post(
            'https://api.openai.com/v1/images/generations',
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'dall-e-3',
                'prompt': prompt,
                'n': 1,
                'size': '1024x1024',
                'quality': 'standard',
            },
            timeout=60,
        )
        resp.raise_for_status()
        image_url = resp.json()['data'][0]['url']
        img_bytes = requests.get(image_url, timeout=30).content
        safe_name = re.sub(r'[^\w가-힣-]', '_', topic)[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.png"
        save_path = IMAGES_DIR / filename
        save_path.write_bytes(img_bytes)
        logger.info(f"자동 이미지 저장: {save_path}")
        return str(save_path)
    except Exception as e:
        logger.error(f"자동 이미지 생성 실패: {e}")
        return None


# ─── unsplash 모드 ───────────────────────────────────

UNSPLASH_KEYWORD_MAP = [
    (['school', 'classroom', 'chalk', 'desk', 'teacher', 'elementary'], 'vintage american school classroom'),
    (['school bus', 'bus'], 'school bus children america'),
    (['cartoon', 'saturday', 'television'], 'vintage family television living room'),
    (['cafeteria', 'lunch'], 'school lunch children cafeteria'),
    (['drive-in', 'movie', 'theater', 'cinema', 'film'], 'drive-in movie theater vintage america'),
    (['car', 'driver', 'license', 'road', 'freedom'], 'classic american car vintage road'),
    (['prom', 'dance', 'high school'], 'vintage high school prom dance america'),
    (['note', 'letter', 'handwritten', 'pen'], 'handwritten letter vintage nostalgia'),
    (['outside', 'play', 'neighborhood', 'kids', 'street'], 'children playing outside neighborhood vintage'),
    (['drugstore', 'soda', 'milkshake', 'diner', 'counter'], 'american diner soda fountain vintage'),
    (['pool', 'swimming', 'summer'], 'summer swimming pool children vintage'),
    (['halloween', 'trick-or-treat'], 'halloween trick or treat children vintage'),
    (['beatles', 'concert', 'music', 'vinyl', 'record'], 'vinyl record player music vintage'),
    (['moon', 'apollo', 'space', 'nasa'], 'moon landing space retro vintage'),
    (['burger', 'milkshake', 'carhop', 'fast food'], 'vintage american burger diner milkshake'),
    (['sunday', 'dinner', 'pot roast', 'mom', 'mother', 'cooking', 'kitchen'], 'family dinner kitchen cooking vintage'),
    (['ice cream', 'ice cream truck', 'popsicle'], 'ice cream children summer street'),
    (['diner', 'jukebox', 'booth'], 'american diner jukebox vintage 1950s'),
    (['christmas', 'presents', 'holiday', 'gifts'], 'christmas family vintage living room'),
    (['fourth of july', 'fireworks', 'sparkler', 'july 4'], 'fourth of july fireworks vintage america'),
    (['road trip', 'station wagon', 'vacation'], 'family road trip station wagon vintage'),
    (['snow', 'sledding', 'winter'], 'children sledding snow winter vintage'),
    (['baseball', 'sport', 'game'], 'vintage american baseball game'),
    (['neighborhood', 'suburb', 'house', 'backyard'], 'american suburban neighborhood vintage house'),
    (['bully', 'kids', 'playing', 'outside'], 'children playing outside summer vintage'),
    (['thanksgiving', 'family', 'table', 'grandma'], 'thanksgiving family dinner table vintage'),
    (['mall', 'shopping', '1980s', 'arcade'], 'shopping mall 1980s america vintage'),
    (['bicycle', 'bike', 'riding'], 'child riding bicycle summer vintage'),
    (['candy', 'store', 'corner'], 'vintage candy store children america'),
    (['barbecue', 'backyard', 'grill'], 'backyard barbecue family summer vintage'),
]

def fetch_unsplash_image(topic: str) -> str | None:
    if not UNSPLASH_ACCESS_KEY:
        logger.error("UNSPLASH_ACCESS_KEY 없음")
        return None
    # 주제 키워드 매핑 — 많이 겹치는 항목 우선
    query = 'vintage american nostalgia family'
    best_match = 0
    topic_words = set(re.findall(r"[a-z']+", topic.lower()))
    for keywords, q in UNSPLASH_KEYWORD_MAP:
        matches = sum(1 for kw in keywords if kw.lower() in topic_words)
        if matches > best_match:
            best_match = matches
            query = q
    try:
        resp = requests.get(
            'https://api.unsplash.com/photos/random',
            params={'query': query, 'orientation': 'landscape'},
            headers={'Authorization': f'Client-ID {UNSPLASH_ACCESS_KEY}'},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        img_url = data['urls']['regular']
        img_bytes = requests.get(img_url, timeout=30).content
        safe_name = re.sub(r'[^\w가-힣-]', '_', topic)[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.jpg"
        save_path = IMAGES_DIR / filename
        save_path.write_bytes(img_bytes)
        logger.info(f"Unsplash 이미지 저장: {save_path} (검색어: {query})")
        return str(save_path)
    except Exception as e:
        logger.error(f"Unsplash 이미지 다운로드 실패: {e}")
        return None


# ─── pexels 모드 ─────────────────────────────────────

PEXELS_KEYWORD_MAP = [
    (['school', 'classroom', 'chalk', 'desk', 'teacher', 'elementary'], 'vintage american school classroom 1960s children'),
    (['school bus', 'bus', 'yellow bus'], 'vintage yellow school bus america children'),
    (['cartoon', 'saturday', 'TV', 'television'], 'vintage family watching television 1960s living room'),
    (['cafeteria', 'lunch', 'pizza', 'food'], 'vintage american school lunch cafeteria children'),
    (['drive-in', 'movie', 'theater', 'cinema', 'film'], 'vintage american drive-in movie theater 1950s 1960s'),
    (['car', 'driver', 'license', 'freedom', 'road'], 'vintage american classic car 1960s 1970s road'),
    (['prom', 'dance', 'high school', 'formal'], 'vintage american high school prom 1960s 1970s dance'),
    (['note', 'letter', 'handwritten', 'pen', 'paper'], 'vintage handwritten letter paper pen nostalgia'),
    (['outside', 'play', 'neighborhood', 'kids', 'street', 'streetlight'], 'vintage american children playing outside neighborhood 1960s'),
    (['drugstore', 'soda fountain', 'milkshake', 'diner', 'counter'], 'vintage american soda fountain diner 1950s milkshake'),
    (['pool', 'swimming', 'summer', 'water'], 'vintage american public swimming pool summer children'),
    (['halloween', 'trick-or-treat', 'costume'], 'vintage halloween trick or treat children neighborhood'),
    (['beatles', 'ed sullivan', 'concert', 'show', 'television'], 'vintage american television show 1960s family watching'),
    (['vinyl', 'record', 'music', 'cassette', 'tape', 'eight-track'], 'vintage vinyl record player music 1960s 1970s'),
    (['moon landing', 'apollo', 'space', 'nasa'], 'vintage television moon landing family watching 1969'),
    (['burger', 'milkshake', 'carhop', 'drive-in restaurant', 'fast food'], 'vintage american drive-in restaurant carhop burger 1950s'),
    (['sunday', 'dinner', 'pot roast', 'mom', 'mother', 'cooking', 'kitchen'], 'vintage american family sunday dinner kitchen mother cooking'),
    (['ice cream', 'ice cream truck', 'popsicle', 'summer'], 'vintage american ice cream truck children summer street'),
    (['diner', 'jukebox', 'booth', 'blue plate', 'restaurant'], 'vintage american diner jukebox 1950s 1960s'),
    (['christmas', 'presents', 'tree', 'holiday', 'gifts'], 'vintage american christmas family presents living room 1960s'),
    (['fourth of july', 'fireworks', 'sparkler', 'july 4', 'independence day'], 'vintage american fourth of july fireworks family picnic'),
    (['road trip', 'station wagon', 'vacation', 'family trip'], 'vintage american family road trip station wagon 1960s 1970s'),
    (['snow', 'sledding', 'snowday', 'winter', 'sled'], 'vintage american children sledding snow winter 1960s'),
    (['baseball', 'sport', 'game', 'stadium'], 'vintage american baseball game stadium 1950s 1960s'),
    (['neighborhood', 'suburb', 'house', 'backyard', 'picket fence'], 'vintage american suburban neighborhood house 1950s 1960s'),
]

def _get_query_for_topic(topic: str) -> str:
    """PEXELS_KEYWORD_MAP에서 topic에 가장 잘 맞는 검색어 반환"""
    query = 'vintage american nostalgia 1960s family neighborhood'
    best_match = 0
    topic_words = set(re.findall(r"[a-z']+", topic.lower()))
    for keywords, q in PEXELS_KEYWORD_MAP:
        matches = sum(1 for kw in keywords if kw.lower() in topic_words)
        if matches > best_match:
            best_match = matches
            query = q
    return query


def fetch_openverse_image(topic: str) -> str | None:
    """
    Openverse API (Flickr Commons + Wikimedia) — 실제 빈티지 미국 사진.
    무료, API 키 불필요.
    """
    query = _get_query_for_topic(topic)
    try:
        # 상업용 가능 라이선스만: CC0(퍼블릭도메인), CC BY, CC BY-SA
        # CC BY-NC / CC BY-ND / CC BY-NC-ND 는 수익 블로그에 사용 불가
        short_query = ' '.join(query.split()[:5])
        resp = requests.get(
            'https://api.openverse.org/v1/images/',
            params={
                'q': short_query,
                'license': 'cc0,pdm,by,by-sa',
                'source': 'flickr,wikimedia',
                'page_size': 20,
                'mature': 'false',
            },
            headers={'User-Agent': 'BlogWriter/1.0 (nostalgia blog automation)'},
            timeout=20,
        )
        resp.raise_for_status()
        results = resp.json().get('results', [])
        if not results:
            logger.warning(f"Openverse 검색 결과 없음: {query} — Pexels로 대체")
            return fetch_pexels_image(topic)
        item = random.choice(results[:10])
        img_url = item.get('url', '')
        if not img_url:
            return fetch_pexels_image(topic)
        img_bytes = requests.get(img_url, timeout=30).content
        safe_name = re.sub(r'[^\w-]', '_', topic)[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.jpg"
        save_path = IMAGES_DIR / filename
        save_path.write_bytes(img_bytes)

        # 출처 정보 저장 (블로그 본문에 삽입하기 위해)
        attribution = {
            'creator': item.get('creator', ''),
            'creator_url': item.get('creator_url', ''),
            'license': item.get('license', ''),
            'license_url': item.get('license_url', ''),
            'source': item.get('foreign_landing_url', ''),
            'title': item.get('title', ''),
        }
        attr_path = save_path.with_suffix('.attribution.json')
        attr_path.write_text(json.dumps(attribution, ensure_ascii=False), encoding='utf-8')

        logger.info(f"Openverse 이미지 저장: {save_path} (검색어: {query}, 라이선스: {attribution['license']})")
        return str(save_path)
    except Exception as e:
        logger.error(f"Openverse 이미지 다운로드 실패: {e} — Pexels로 대체")
        return fetch_pexels_image(topic)


def fetch_pexels_image(topic: str) -> str | None:
    if not PEXELS_API_KEY:
        logger.error("PEXELS_API_KEY 없음")
        return None
    query = _get_query_for_topic(topic)
    try:
        resp = requests.get(
            'https://api.pexels.com/v1/search',
            params={'query': query, 'per_page': 15, 'orientation': 'landscape'},
            headers={'Authorization': PEXELS_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get('photos', [])
        if not photos:
            logger.warning(f"Pexels 검색 결과 없음: {query}")
            return None
        photo = random.choice(photos[:10])
        img_url = photo['src']['large']
        img_bytes = requests.get(img_url, timeout=30).content
        safe_name = re.sub(r'[^\w-]', '_', topic)[:50]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.jpg"
        save_path = IMAGES_DIR / filename
        save_path.write_bytes(img_bytes)
        logger.info(f"Pexels 이미지 저장: {save_path} (검색어: {query})")
        return str(save_path)
    except Exception as e:
        logger.error(f"Pexels 이미지 다운로드 실패: {e}")
        return None


# ─── manual 모드 ──────────────────────────────────────

def process_manual_mode(topic: str, description: str = '') -> str:
    """글 발행 시점에 프롬프트 1개 Telegram 전송 (파일 저장은 사용자 직접)"""
    prompt = build_cartoon_prompt(topic, description)
    safe_name = re.sub(r'[^\w가-힣-]', '_', topic)[:50]
    expected_path = IMAGES_DIR / f"{datetime.now().strftime('%Y%m%d')}_{safe_name}.png"
    send_telegram(
        f"🎨 <b>[만평 이미지 요청 — manual]</b>\n\n"
        f"📌 주제: <b>{topic}</b>\n\n"
        f"📝 프롬프트:\n<code>{prompt}</code>\n\n"
        f"이미지 생성 후 아래 경로에 저장해주세요:\n"
        f"<code>{expected_path}</code>"
    )
    logger.info(f"manual 모드 프롬프트 전송: {topic}")
    return str(expected_path)


# ─── 메인 진입점 ──────────────────────────────────────

def process(article: dict) -> str | None:
    """
    한컷 코너 글에 대해 모드에 따라 이미지 처리.
    Returns: 이미지 경로 (request 모드에서는 None — 비동기로 나중에 수령)
    """
    if article.get('corner') != '한컷':
        return None

    topic = article.get('title', '')
    description = article.get('meta', '')
    logger.info(f"이미지봇 실행: {topic} (모드: {IMAGE_MODE})")

    if IMAGE_MODE == 'pexels':
        return fetch_pexels_image(topic)

    elif IMAGE_MODE == 'unsplash':
        return fetch_unsplash_image(topic)

    elif IMAGE_MODE == 'auto':
        prompt = build_cartoon_prompt(topic, description)
        image_path = generate_image_auto(prompt, topic)
        if image_path:
            send_telegram(
                f"🎨 <b>[자동 이미지 생성 완료]</b>\n\n📌 {topic}\n경로: <code>{image_path}</code>"
            )
        return image_path

    elif IMAGE_MODE == 'request':
        item = add_pending_prompt(topic, description, article_ref=article.get('_source_file', ''))
        send_telegram(
            f"🎨 <b>[이미지 제작 요청 추가됨]</b>\n\n"
            f"📌 주제: <b>{topic}</b>\n"
            f"번호: <b>#{item['id']}</b>\n\n"
            f"/imgpick {item['id']} — 이 주제 프롬프트 받기\n"
            f"/images — 전체 대기 목록 보기"
        )
        return None  # 이미지는 나중에 Telegram으로 수령

    else:  # manual (기본)
        return process_manual_mode(topic, description)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'batch':
        send_prompt_batch()
    else:
        sample = {'corner': '한컷', 'title': 'AI가 직업을 빼앗는다?', 'meta': ''}
        print(process(sample))
