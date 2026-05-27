# The 4th Path: ⟨H⊕A⟩ ↦ Ω
# Human × AI → a better world.
# 22B Labs | the4thpath.com
"""
발행봇 (publisher_bot.py)
역할: AI가 작성한 글을 Blogger에 자동 발행
- 마크다운 → HTML 변환
- 목차 자동 생성
- AdSense 플레이스홀더 삽입
- Schema.org Article JSON-LD
- 안전장치 (팩트체크/위험 키워드/출처 부족 → 수동 검토)
- Blogger API v3 발행
- Search Console URL 제출
- Telegram 알림
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import markdown
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / 'config'
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'logs'
TOKEN_PATH = BASE_DIR / 'token.json'
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'publisher.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
BLOG_MAIN_ID = os.getenv('BLOG_MAIN_ID', '')

SCOPES = [
    'https://www.googleapis.com/auth/blogger',
    'https://www.googleapis.com/auth/webmasters',
]

BLOG_SITEMAP_URL = 'https://kang121722.blogspot.com/sitemap.xml'


def load_config(filename: str) -> dict:
    with open(CONFIG_DIR / filename, 'r', encoding='utf-8') as f:
        return json.load(f)


# ─── Google 인증 ─────────────────────────────────────

def get_google_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'w') as f:
                f.write(creds.to_json())
        else:
            # GitHub Actions 환경: 환경변수에서 직접 인증
            client_id = os.getenv('GOOGLE_CLIENT_ID', '')
            client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '')
            refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN', '')
            if client_id and client_secret and refresh_token:
                creds = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=SCOPES,
                )
                creds.refresh(Request())
            else:
                raise RuntimeError("Google 인증 실패. scripts/get_token.py 를 먼저 실행하세요.")
    if not creds or not creds.valid:
        raise RuntimeError("Google 인증 실패. scripts/get_token.py 를 먼저 실행하세요.")
    return creds


# ─── 안전장치 ─────────────────────────────────────────

def check_safety(article: dict, safety_cfg: dict) -> tuple[bool, str]:
    """
    수동 검토가 필요한지 판단.
    Returns: (needs_review, reason)
    """
    corner = article.get('corner', '')
    body = article.get('body', '')
    sources = article.get('sources', [])
    quality_score = article.get('quality_score', 100)

    # 팩트체크 코너는 무조건 수동 검토
    manual_corners = safety_cfg.get('always_manual_review', ['팩트체크'])
    if corner in manual_corners:
        return True, f'코너 "{corner}" 는 항상 수동 검토 필요'

    # 위험 키워드 감지
    all_keywords = (
        safety_cfg.get('crypto_keywords', []) +
        safety_cfg.get('criticism_keywords', []) +
        safety_cfg.get('investment_keywords', []) +
        safety_cfg.get('legal_keywords', [])
    )
    for kw in all_keywords:
        if kw in body:
            return True, f'위험 키워드 감지: "{kw}"'

    # 품질 점수 미달 (출처 개수 체크 제거 — AI 생성 글은 출처 보장 불가)
    min_score = safety_cfg.get('min_quality_score_for_auto', 75)
    if quality_score < min_score:
        return True, f'품질 점수 {quality_score}점 (자동 발행 최소: {min_score}점)'

    return False, ''


# ─── HTML 변환 ─────────────────────────────────────────

def markdown_to_html(md_text: str) -> str:
    """마크다운 → HTML 변환 (목차 없음)"""
    md = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'attr_list'],
    )
    html = md.convert(md_text)
    return html, ''  # toc 항상 빈 값


def add_image_alt_tags(html: str, title: str, tags: list) -> str:
    """alt 없는 img 태그에 자동으로 alt 속성 추가 (SEO)"""
    soup = BeautifulSoup(html, 'html.parser')
    keyword = title.split('–')[0].strip() if '–' in title else title[:60]
    for i, img in enumerate(soup.find_all('img')):
        if not img.get('alt'):
            suffix = f', {tags[i % len(tags)]}' if tags else ''
            img['alt'] = f'{keyword}{suffix}'
    return str(soup)


def add_internal_links(category_key: str = None, current_title: str = '') -> str:
    """카테고리 사일로 내부링크 — 동일 카테고리 글 최대 3개를 Related Posts 박스로 반환.
    current_title: 현재 발행 글 제목 — 자기 자신 링크 방지용.
    타 카테고리 보충 없음 (사일로 철저 준수). 발행 글 없으면 빈 문자열 반환."""
    import random as _random
    published_dir = DATA_DIR / 'published'
    if not published_dir.exists() or not category_key:
        return ''

    all_records = sorted(published_dir.glob('*.json'), reverse=True)

    def _load(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return None

    same_cat = []
    for p in all_records:
        rec = _load(p)
        if not rec:
            continue
        if rec.get('url') and rec.get('title') and rec.get('category_key') == category_key:
            # 현재 글 자기 자신 제외
            if current_title and rec['title'].strip() == current_title.strip():
                continue
            same_cat.append(rec)

    if not same_cat:
        return ''

    # 최대 3개 무작위 선택
    picked = _random.sample(same_cat, min(3, len(same_cat)))

    items_html = ''.join(
        f'<li style="margin-bottom:8px;">'
        f'<a href="{r["url"]}" rel="bookmark" '
        f'style="color:#1d4ed8;text-decoration:underline;font-size:15px;">'
        f'{r["title"]}</a>'
        f'</li>'
        for r in picked
    )
    return (
        '<div style="margin:32px 0;padding:20px 24px;'
        'background:#f0f7ff;border-left:4px solid #3b82f6;border-radius:8px;">'
        '<p style="margin:0 0 12px;font-size:14px;font-weight:bold;'
        'color:#1e40af;text-transform:uppercase;letter-spacing:.05em;">📖 Keep Reading</p>'
        f'<ul style="margin:0;padding-left:18px;">{items_html}</ul>'
        '</div>'
    )


def build_toc(html: str) -> str:
    """본문 H2 태그로 목차(TOC) 생성 + 각 H2에 id 앵커 삽입.
    H2가 3개 미만이면 빈 문자열 반환 (짧은 글엔 목차 불필요)."""
    import re as _re
    soup = BeautifulSoup(html, 'html.parser')
    h2_tags = soup.find_all('h2')
    if len(h2_tags) < 3:
        return '', html  # (toc_html, body_html)

    items = []
    for i, tag in enumerate(h2_tags):
        slug = _re.sub(r'[^a-z0-9]+', '-', tag.get_text().lower()).strip('-')
        anchor_id = f'toc-{i+1}-{slug[:40]}'
        tag['id'] = anchor_id
        items.append((anchor_id, tag.get_text()))

    li_html = ''.join(
        f'<li style="margin-bottom:6px;">'
        f'<a href="#{aid}" style="color:#1d4ed8;text-decoration:none;font-size:14px;">'
        f'{text}</a></li>'
        for aid, text in items
    )
    toc = (
        '<nav style="margin:0 0 28px;padding:18px 22px;'
        'background:#f8f9fa;border:1px solid #e2e8f0;border-radius:8px;">'
        '<p style="margin:0 0 10px;font-size:13px;font-weight:bold;'
        'color:#374151;text-transform:uppercase;letter-spacing:.06em;">In This Article</p>'
        f'<ul style="margin:0;padding-left:18px;list-style:disc;">{li_html}</ul>'
        '</nav>'
    )
    return toc, str(soup)  # 앵커 id가 추가된 body도 반환


def add_reading_time(html: str) -> str:
    """글 상단에 읽기 예상 시간 추가 (SEO 체류시간 개선)"""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text()
    word_count = len(text.split())
    minutes = max(1, round(word_count / 200))
    badge = (
        f'<p style="color:#888;font-size:13px;margin-bottom:16px;">'
        f'⏱ {minutes} min read &nbsp;·&nbsp; {word_count:,} words'
        f'</p>'
    )
    # 첫 번째 태그 앞에 삽입
    first_tag = soup.find(['h2', 'p'])
    if first_tag:
        first_tag.insert_before(BeautifulSoup(badge, 'html.parser'))
    return str(soup)


def add_faq_schema(article: dict, faq_items: list) -> str:
    """FAQ Schema.org JSON-LD 생성 (구글 FAQ 스니펫 노출용)"""
    if not faq_items:
        return ''
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.get('q', ''),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item.get('a', '')
                }
            }
            for item in faq_items if item.get('q') and item.get('a')
        ]
    }
    if not schema['mainEntity']:
        return ''
    return f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n</script>'


def parse_faq_from_body(body_html: str) -> list:
    """본문 HTML에서 FAQ 섹션 파싱.
    지원 패턴:
      1. <h3>Q: ...</h3><p>A: ...</p>   ← 시스템 프롬프트 지정 포맷
      2. <div class="faq-item">...      ← 대안 포맷
      3. <strong>Q: ...</strong>...     ← 레거시 포맷
    """
    import re as _re
    soup = BeautifulSoup(body_html, 'html.parser')
    faq_items = []

    # 패턴 1: <h3>Q: ...</h3> + 다음 <p>
    for h3 in soup.find_all('h3'):
        text = h3.get_text(strip=True)
        if not _re.match(r'^Q[:\.]?\s*', text, _re.IGNORECASE):
            continue
        q_text = _re.sub(r'^Q[:\.]?\s*', '', text, flags=_re.IGNORECASE).strip()
        # 바로 다음 sibling p 또는 div 찾기
        nxt = h3.find_next_sibling(['p', 'div'])
        if not nxt:
            continue
        a_raw = nxt.get_text(strip=True)
        a_text = _re.sub(r'^A[:\.]?\s*', '', a_raw, flags=_re.IGNORECASE).strip()
        if q_text and a_text:
            faq_items.append({'q': q_text, 'a': a_text})
        if len(faq_items) >= 6:
            break

    # 패턴 3: 레거시 <strong>Q:...</strong> (패턴 1 미발견 시)
    if not faq_items:
        for m in _re.finditer(
            r'<strong>Q[:\.]?\s*(.+?)</strong>\s*<[^>]+>\s*A[:\.]?\s*(.+?)</[^>]+>',
            body_html, _re.DOTALL
        ):
            q = _re.sub(r'<[^>]+>', '', m.group(1)).strip()
            a = _re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if q and a:
                faq_items.append({'q': q, 'a': a})
            if len(faq_items) >= 6:
                break

    return faq_items


def insert_adsense_placeholders(html: str) -> str:
    """두 번째 H2 뒤와 결론 섹션 앞에 AdSense 플레이스홀더 삽입"""
    AD_SLOT_1 = ''
    AD_SLOT_2 = ''

    soup = BeautifulSoup(html, 'html.parser')
    h2_tags = soup.find_all('h2')

    # 두 번째 H2 뒤에 AD_SLOT_1 삽입
    if len(h2_tags) >= 2:
        second_h2 = h2_tags[1]
        ad_tag = BeautifulSoup(AD_SLOT_1, 'html.parser')
        second_h2.insert_after(ad_tag)

    # 결론 H2 앞에 AD_SLOT_2 삽입
    for h2 in soup.find_all('h2'):
        if any(kw in h2.get_text() for kw in ['결론', '마무리', '정리', '요약', 'conclusion']):
            ad_tag2 = BeautifulSoup(AD_SLOT_2, 'html.parser')
            h2.insert_before(ad_tag2)
            break

    return str(soup)


def build_json_ld(article: dict, blog_url: str = '') -> str:
    """Schema.org Article JSON-LD 생성 (OG 태그는 Blogger 테마에서 처리)"""
    title = article.get('title', '')
    description = article.get('meta', '')
    tags = article.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    keywords = ', '.join(tags)

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "keywords": keywords,
        "datePublished": datetime.now(timezone.utc).isoformat(),
        "dateModified": datetime.now(timezone.utc).isoformat(),
        "author": {
            "@type": "Person",
            "name": "Senior Memories"
        },
        "publisher": {
            "@type": "Organization",
            "name": "Senior Memories",
            "logo": {
                "@type": "ImageObject",
                "url": ""
            }
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": blog_url
        }
    }
    return f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n</script>'


CTA_BLOCKS = {
    'A': {
        'headline': 'Want to see your actual Medigap rates?',
        'subtext':  'Compare Plan G and Plan N quotes by ZIP code. Free, takes about 2 minutes, no sales calls required.',
        'button':   '🔍 Compare My Rates',
        'link_env': 'LINK_MEDICARE',
    },
    'B': {
        'headline': 'Not sure which Social Security strategy fits your situation?',
        'subtext':  'Compare claiming ages side by side and see the lifetime difference in real dollars. Free tool, no account needed.',
        'button':   '📊 Run My Retirement Numbers',
        'link_env': 'LINK_RETIREMENT',
    },
    'C': {
        'headline': 'Want to make your home safer before a fall happens?',
        'subtext':  'Browse top-rated grab bars, stair lifts, and medical alert systems for seniors. Most ship in 2 days.',
        'button':   '🏠 See Top-Rated Safety Products',
        'link_env': 'LINK_AGING',
    },
    'D': {
        'headline': 'Paying too much for your prescriptions?',
        'subtext':  'Enter your medications and ZIP code to find the lowest Part D plan price in your area. Takes 2 minutes.',
        'button':   '💊 Find My Lowest Drug Price',
        'link_env': 'LINK_HEALTH',
    },
}


def build_cta_html(category_key: str) -> str:
    """카테고리별 리드젠 CTA 블록 생성.
    실제 링크가 설정된 경우에만 출력 — 미설정/더미 링크면 빈 문자열 반환."""
    cta = CTA_BLOCKS.get(category_key)
    if not cta:
        return ''
    link = os.getenv(cta['link_env'], '')
    # 링크 없거나 플레이스홀더면 CTA 블록 자체를 출력하지 않음 (미완성 블로그 인상 방지)
    if not link or link.startswith('https://YOUR_') or 'example.com' in link:
        return ''
    btn_style = (
        'background-color:#0056b3;color:white;padding:16px 32px;'
        'text-decoration:none;font-size:18px;font-weight:bold;border-radius:8px;'
        'display:inline-block;box-shadow:0 4px 6px rgba(0,0,0,0.1);'
    )
    return (
        '<div style="text-align:center;margin:35px 0;padding:20px;'
        'background-color:#f8f9fa;border:1px solid #e9ecef;border-radius:10px;">'
        f'<h3 style="margin-top:0;color:#333;">{cta["headline"]}</h3>'
        f'<p style="color:#555;font-size:16px;margin-bottom:20px;">{cta["subtext"]}</p>'
        f'<a href="{link}" style="{btn_style}">{cta["button"]}</a>'
        '</div>'
    )


def build_full_html(article: dict, body_html: str, toc_html: str, blog_url: str = '') -> str:
    """최종 HTML 조합: JSON-LD + OG + 읽기시간 + 본문 + FAQ스키마 + 면책 문구 + CTA"""
    json_ld = build_json_ld(article, blog_url)
    disclaimer = article.get('disclaimer', '')

    # FAQ 스키마 파싱 및 추가
    faq_items = parse_faq_from_body(body_html)
    faq_schema = add_faq_schema(article, faq_items)

    # JSON-LD script는 Blogger API가 보안상 거부 → 제외
    html_parts = []
    if toc_html:
        html_parts.append(toc_html)
    html_parts.append(body_html)

    # FAQ Schema.org JSON-LD (FAQPage 스니펫 — Google 검색 노출용)
    faq_items = parse_faq_from_body(body_html)
    faq_schema = add_faq_schema(article, faq_items)
    if faq_schema:
        html_parts.append(faq_schema)
        logger.info(f'[SEO] FAQ Schema 삽입: {len(faq_items)}개 Q&A')
    if disclaimer:
        html_parts.append(f'<hr/><p class="disclaimer"><small>{disclaimer}</small></p>')

    # 카테고리별 면책 문구 자동 삽입
    category_key = article.get('category_key', '')
    if category_key in ('A', 'B'):
        disclaimer_text = (
            '<hr style="margin:32px 0 16px;border:none;border-top:1px solid #e0e0e0;"/>'
            '<p style="font-size:12px;color:#999;line-height:1.6;">'
            '<strong>Disclaimer:</strong> This article is for informational purposes only and does not constitute '
            'financial, legal, or medical advice. Medicare rules, tax laws, and Social Security benefit amounts '
            'change annually. Always consult a licensed financial advisor, Medicare specialist, or Social Security '
            'Administration representative before making decisions about your benefits, retirement income, or estate planning.'
            '</p>'
        )
    elif category_key == 'C':
        disclaimer_text = (
            '<hr style="margin:32px 0 16px;border:none;border-top:1px solid #e0e0e0;"/>'
            '<p style="font-size:12px;color:#999;line-height:1.6;">'
            '<strong>Disclaimer:</strong> This article is for informational purposes only. '
            'Product availability, pricing, and features may vary. Consult a healthcare professional '
            'or occupational therapist before making home modification or medical device decisions.'
            '</p>'
        )
    elif category_key == 'D':
        disclaimer_text = (
            '<hr style="margin:32px 0 16px;border:none;border-top:1px solid #e0e0e0;"/>'
            '<p style="font-size:12px;color:#999;line-height:1.6;">'
            '<strong>Disclaimer:</strong> This article is for general informational purposes only '
            'and does not constitute medical or nutritional advice. Exercise and dietary needs vary '
            'by individual health condition. Always consult your physician or a registered dietitian '
            'before starting a new diet or exercise program.'
            '</p>'
        )
    else:
        disclaimer_text = ''

    if disclaimer_text:
        html_parts.append(disclaimer_text)

    # 카테고리별 CTA 블록 (리드젠 링크 설정된 경우에만 삽입)
    cta_html = build_cta_html(category_key)
    if cta_html:
        html_parts.append(cta_html)

    # 카테고리 사일로 연관 칼럼 (CTA 바로 아래, 동일 카테고리만)
    related_html = add_internal_links(
        category_key=category_key,
        current_title=article.get('title', ''),  # 자기 자신 링크 방지
    )
    if related_html:
        html_parts.append(related_html)

    return '\n'.join(html_parts)


# ─── Blogger API ──────────────────────────────────────

def publish_to_blogger(article: dict, html_content: str, creds: Credentials) -> dict:
    """Blogger API v3로 글 발행"""
    service = build('blogger', 'v3', credentials=creds)
    blog_id = BLOG_MAIN_ID

    tags = article.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    # corner(카테고리명)은 라벨 제외 — 너무 많은 라벨 조합이 Blogger 400 유발
    # AI 생성 태그 최대 4개 + 고정 카테고리 라벨로 총 8개 이하 유지
    labels = list(dict.fromkeys(filter(None, tags)))[:4]  # AI 태그 최대 4개 (순서 유지 dedup)
    # 고정 카테고리 라벨 추가 (중복 제거)
    for fixed in article.get('_fixed_labels', []):
        if fixed and fixed not in labels:
            labels.append(fixed)
    labels = labels[:8]  # 안전장치: 최대 8개

    title = article.get('title', '').strip()[:150]  # 제목 길이 제한

    body = {
        'title': title,
        'content': html_content,
        'labels': labels,
    }

    # 썸네일 이미지 등록 (Blogger 포스트 목록에 섬네일 표시)
    img_url = article.get('_img_url')
    if img_url:
        body['images'] = [{'url': img_url}]

    logger.info(f'Blogger 전송: title={title[:60]}, labels={len(labels)}개, content={len(html_content)}자')
    logger.info(f'Labels 목록: {labels}')
    # 디버그: 전송 전 HTML 저장
    _debug_path = Path(__file__).parent.parent / 'logs' / 'last_post_debug.html'
    _debug_path.write_text(html_content, encoding='utf-8')
    # 디버그: 전송 body 전체 저장
    import json as _json
    (_debug_path.parent / 'last_post_body.json').write_text(
        _json.dumps({'title': title, 'labels': labels, 'content_len': len(html_content)}, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    result = service.posts().insert(
        blogId=blog_id,
        body=body,
        isDraft=False,
    ).execute()

    return result


def submit_to_search_console(url: str, creds: Credentials):
    """발행 직후 Google Search Console에 전체 sitemap 재제출.
    Blogger sitemap은 페이지당 25개 → page=1~6까지 모두 제출해야
    122개+ 글이 전부 구글에 노출됨."""
    if not url:
        return

    SITE_URL = 'https://kang121722.blogspot.com/'
    BASE_SITEMAP = 'https://kang121722.blogspot.com/sitemap.xml'

    try:
        sc = build('webmasters', 'v3', credentials=creds)

        # 전체 sitemap 페이지 제출 (페이지당 25개, 최대 6페이지 = 150개 커버)
        sitemaps_to_submit = [BASE_SITEMAP] + [
            f'{BASE_SITEMAP}?page={p}' for p in range(2, 7)
        ]
        for feedpath in sitemaps_to_submit:
            try:
                sc.sitemaps().submit(siteUrl=SITE_URL, feedpath=feedpath).execute()
                logger.info(f'Search Console sitemap 제출: {feedpath}')
            except Exception as e:
                logger.warning(f'sitemap 제출 실패 ({feedpath}): {e}')

    except Exception as e:
        logger.warning(f'Search Console 연결 실패: {e}')


# ─── Telegram ────────────────────────────────────────

def send_telegram(text: str, parse_mode: str = 'HTML'):
    """Telegram 메시지 전송 (토큰 미설정 시 조용히 건너뜀)"""
    if (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID
            or 'your_telegram' in TELEGRAM_BOT_TOKEN.lower()
            or 'your_telegram' in TELEGRAM_CHAT_ID.lower()):
        return  # 미설정 상태 — 에러 없이 건너뜀
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram 전송 실패: {e}")


def send_pending_review_alert(article: dict, reason: str):
    """수동 검토 대기 알림 (Telegram)"""
    title = article.get('title', '(제목 없음)')
    corner = article.get('corner', '')
    preview = article.get('body', '')[:300].replace('<', '&lt;').replace('>', '&gt;')
    msg = (
        f"🔍 <b>[수동 검토 필요]</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"코너: {corner}\n"
        f"사유: {reason}\n\n"
        f"미리보기:\n{preview}...\n\n"
        f"명령: <code>승인</code> 또는 <code>거부</code>"
    )
    send_telegram(msg)


# ─── 발행 이력 ───────────────────────────────────────

def log_published(article: dict, post_result: dict):
    """발행 이력 저장"""
    published_dir = DATA_DIR / 'published'
    published_dir.mkdir(exist_ok=True)
    record = {
        'title': article.get('title', ''),
        'corner': article.get('corner', ''),
        'category_key': article.get('category_key', ''),   # A/B/C 카테고리 키
        'url': post_result.get('url', ''),
        'post_id': post_result.get('id', ''),
        'published_at': datetime.now(timezone.utc).isoformat(),
        'quality_score': article.get('quality_score', 0),
        'tags': article.get('tags', []),
        'sources': article.get('sources', []),
    }
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{record['post_id']}.json"
    with open(published_dir / filename, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def save_pending_review(article: dict, reason: str):
    """수동 검토 대기 글 저장"""
    pending_dir = DATA_DIR / 'pending_review'
    pending_dir.mkdir(exist_ok=True)
    record = {**article, 'pending_reason': reason, 'created_at': datetime.now().isoformat()}
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_pending.json"
    with open(pending_dir / filename, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return pending_dir / filename


def load_pending_review_file(filepath: str) -> dict:
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


# ─── 메인 발행 함수 ──────────────────────────────────

def publish(article: dict) -> bool:
    """
    article: OpenClaw blog-writer가 출력한 파싱된 글 dict
    {
        title, meta, slug, tags, corner, body (markdown),
        coupang_keywords, sources, disclaimer, quality_score
    }
    Returns: True(발행 성공) / False(수동 검토 대기)
    """
    logger.info(f"발행 시도: {article.get('title', '')}")
    safety_cfg = load_config('safety_keywords.json')

    # 안전장치 검사
    needs_review, review_reason = check_safety(article, safety_cfg)
    if needs_review:
        logger.warning(f"수동 검토 대기: {review_reason}")
        save_pending_review(article, review_reason)
        send_pending_review_alert(article, review_reason)
        return False

    # 변환봇이 미리 생성한 HTML이 있으면 재사용, 없으면 직접 변환
    tags_list = article.get('tags', [])
    if isinstance(tags_list, str):
        tags_list = [t.strip() for t in tags_list.split(',')]

    if article.get('_html_content'):
        body_html = article['_html_content']
    else:
        body_html, _ = markdown_to_html(article.get('body', ''))

    # SEO 처리
    body_html = add_image_alt_tags(body_html, article.get('title', ''), tags_list)
    body_html = add_reading_time(body_html)
    body_html = insert_adsense_placeholders(body_html)

    # TOC 생성 (H2 3개 이상 글에만)
    toc_result = build_toc(body_html)
    if isinstance(toc_result, tuple):
        toc_html, body_html = toc_result  # H2에 id 앵커도 함께 적용
    else:
        toc_html = ''

    # 내부링크는 build_full_html() 내부에서 CTA 아래에 삽입 (카테고리 사일로)
    full_html = build_full_html(article, body_html, toc_html)

    # src/href 속성 내 &amp; → & 복원 (Blogger API가 &amp; 포함 URL을 400으로 거부)
    import re as _re
    full_html = _re.sub(
        r'((?:src|href)="[^"]*")',
        lambda m: m.group(1).replace('&amp;', '&'),
        full_html,
    )

    # Google 인증
    try:
        creds = get_google_credentials()
    except RuntimeError as e:
        logger.error(str(e))
        return False

    # Blogger 발행
    try:
        post_result = publish_to_blogger(article, full_html, creds)
        post_url = post_result.get('url', '')
        logger.info(f"발행 완료: {post_url}")
    except Exception as e:
        logger.error(f"Blogger 발행 실패: {e}")
        return False

    # Search Console 제출
    if post_url:
        submit_to_search_console(post_url, creds)

    # 발행 이력 저장
    log_published(article, post_result)

    # Telegram 알림
    title = article.get('title', '')
    corner = article.get('corner', '')
    send_telegram(
        f"✅ <b>발행 완료!</b>\n\n"
        f"📌 <b>{title}</b>\n"
        f"코너: {corner}\n"
        f"URL: {post_url}"
    )

    return True


def approve_pending(filepath: str) -> bool:
    """수동 검토 대기 글 승인 후 발행"""
    try:
        article = load_pending_review_file(filepath)
        article.pop('pending_reason', None)
        article.pop('created_at', None)

        # 안전장치 우회하여 강제 발행
        body_html, toc_html = markdown_to_html(article.get('body', ''))
        body_html = insert_adsense_placeholders(body_html)
        full_html = build_full_html(article, body_html, toc_html)

        creds = get_google_credentials()
        post_result = publish_to_blogger(article, full_html, creds)
        post_url = post_result.get('url', '')
        log_published(article, post_result)

        # 대기 파일 삭제
        Path(filepath).unlink(missing_ok=True)

        send_telegram(
            f"✅ <b>[수동 승인] 발행 완료!</b>\n\n"
            f"📌 {article.get('title', '')}\n"
            f"URL: {post_url}"
        )
        logger.info(f"수동 승인 발행 완료: {post_url}")
        return True
    except Exception as e:
        logger.error(f"승인 발행 실패: {e}")
        return False


def reject_pending(filepath: str):
    """수동 검토 대기 글 거부 (파일 삭제)"""
    try:
        article = load_pending_review_file(filepath)
        Path(filepath).unlink(missing_ok=True)
        send_telegram(f"🗑 <b>[거부]</b> {article.get('title', '')} — 폐기됨")
        logger.info(f"수동 검토 거부: {filepath}")
    except Exception as e:
        logger.error(f"거부 처리 실패: {e}")


def get_pending_list() -> list[dict]:
    """수동 검토 대기 목록 반환"""
    pending_dir = DATA_DIR / 'pending_review'
    pending_dir.mkdir(exist_ok=True)
    result = []
    for f in sorted(pending_dir.glob('*_pending.json')):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            data['_filepath'] = str(f)
            result.append(data)
        except Exception:
            pass
    return result


if __name__ == '__main__':
    # 테스트용: 샘플 아티클 발행 시도
    sample = {
        'title': '테스트 글',
        'meta': '테스트 메타 설명',
        'slug': 'test-article',
        'tags': ['테스트', 'AI'],
        'corner': '쉬운세상',
        'body': '## 제목\n\n본문 내용입니다.\n\n## 결론\n\n마무리입니다.',
        'coupang_keywords': ['키보드'],
        'sources': [
            {'url': 'https://example.com/1', 'title': '출처1', 'date': '2026-03-24'},
            {'url': 'https://example.com/2', 'title': '출처2', 'date': '2026-03-24'},
        ],
        'disclaimer': '',
        'quality_score': 80,
    }
    result = publish(sample)
    print('발행 결과:', result)
