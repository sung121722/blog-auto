"""
scan_hook_quality.py — 블로그 전체 글 첫 단락 품질 스캔
Blogger API로 전체 글 목록 가져오기 → 노스탤지아 오프닝 / 얇은 콘텐츠 감지
"""
import sys, json, re, time
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

import requests as _req
from bs4 import BeautifulSoup
from bots.publisher_bot import get_google_credentials
from googleapiclient.discovery import build
import os

BLOG_ID = os.getenv('BLOG_MAIN_ID', '')

# ── 감지 패턴 ─────────────────────────────────────────────────

NOSTALGIA_RE = re.compile(
    r'^.{0,400}(?:'
    r'remember those|remember when|back in the \d{4}|those were the days'
    r'|saturday evening|sunday afternoon|summer of \d{4}'
    r'|growing up|as a kid|when i was young|my (mother|father|grandfather|grandmother)'
    r'|the smell of|the sound of|the taste of'
    r'|do you remember|picture this|close your eyes'
    r')',
    re.IGNORECASE | re.DOTALL
)

OFF_TOPIC_RE = re.compile(
    r'\b(block party|potato salad|baseball|apple pie|lincoln logs|tinker toys'
    r'|erector set|sparkler|fourth of july|thanksgiving dinner'
    r'|neighborhood kids|front porch|screen door|little league|soda fountain'
    r'|drive.in|corner store|five.and.dime)\b',
    re.IGNORECASE
)

def fetch_first_text(url: str) -> tuple[str, int]:
    """(first_400_chars, word_count) 반환 — 사이드바 제외한 본문만"""
    try:
        r = _req.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        article = (soup.find('div', class_='post-body')
                   or soup.find('article')
                   or soup.find('div', class_='entry-content'))
        if not article:
            return 'NO_BODY', 0
        text = article.get_text(' ', strip=True)
        return text[:400], len(text.split())
    except Exception as e:
        return f'ERROR:{e}', 0

# ── Blogger API로 전체 글 목록 가져오기 ───────────────────────
print('Blogger API 연결 중...')
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

all_posts = []
page_token = None
page_num = 0

while True:
    page_num += 1
    kwargs = dict(
        blogId=BLOG_ID,
        maxResults=100,          # Blogger API 실제 한도 100
        fetchBodies=False,       # 본문은 직접 HTTP로 가져옴
        fetchImages=False,
        fields='items(id,title,url,labels),nextPageToken',
    )
    if page_token:
        kwargs['pageToken'] = page_token

    resp = service.posts().list(**kwargs).execute()
    batch = resp.get('items', [])
    all_posts.extend(batch)
    print(f'  페이지 {page_num}: {len(batch)}개 수집 (누계 {len(all_posts)}개)')

    page_token = resp.get('nextPageToken')
    if not page_token:
        break

print(f'\n총 {len(all_posts)}개 글 발견 → 스캔 시작...\n')

issues = []
for i, post in enumerate(all_posts):
    url   = post.get('url', '')
    title = post.get('title', '')
    labels = post.get('labels', [])

    if not url:
        continue

    first_400, wc = fetch_first_text(url)

    if first_400.startswith('ERROR') or first_400 == 'NO_BODY':
        print(f'[{i+1:03d}] SKIP  {title[:55]}')
        time.sleep(0.5)
        continue

    found = []

    if NOSTALGIA_RE.search(first_400):
        found.append('노스탤지아오프닝')

    if OFF_TOPIC_RE.search(first_400):
        found.append('주제무관오프닝')

    if wc < 900:
        found.append(f'얇은콘텐츠({wc}단어)')
    elif wc < 1100:
        found.append(f'짧은콘텐츠({wc}단어)')

    status = '⚠️  ' + ' + '.join(found) if found else '✅'
    print(f'[{i+1:03d}] {status:<45} {title[:55]}')

    if found:
        issues.append({
            'post_id': post.get('id', ''),
            'url': url,
            'title': title,
            'labels': labels,
            'issues': found,
            'word_count': wc,
            'first_sentence': first_400[:200],
        })

    time.sleep(0.6)

# ── 결과 출력 ─────────────────────────────────────────────────
print(f'\n{"="*70}')
print(f'문제 있는 글: {len(issues)}개 / 전체 {len(all_posts)}개')

if issues:
    print()
    nostalgia = [x for x in issues if '노스탤지아오프닝' in x['issues'] or '주제무관오프닝' in x['issues']]
    thin      = [x for x in issues if any('콘텐츠' in iss for iss in x['issues'])]
    both      = [x for x in issues if len(x['issues']) >= 2]

    print(f'  노스탤지아/무관 오프닝: {len(nostalgia)}개')
    print(f'  얇은/짧은 콘텐츠:       {len(thin)}개')
    print(f'  복합 문제:              {len(both)}개')
    print()

    for item in issues:
        print(f'  {item["title"][:60]}')
        print(f'    문제: {" + ".join(item["issues"])}')
        print(f'    첫문장: {item["first_sentence"][:100]}...')
        print(f'    URL: {item["url"]}')
        print()

    out = Path('data/hook_issues.json')
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'결과 저장: {out}')
else:
    print('✅ 문제 없음')
