"""
fix_add_keep_reading.py
Keep Reading 섹션이 없는 발행 글에 연관글 추가
사용법: py scripts\fix_add_keep_reading.py <blog_url_or_keyword> <category_key>
예시:   py scripts\fix_add_keep_reading.py "signs-your-parent-needs-memory-care" A
        py scripts\fix_add_keep_reading.py "how-to-split-ira-in-divorce" B
"""
import sys, re
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

from bots.publisher_bot import get_google_credentials, add_internal_links
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import os

BLOG_ID = os.getenv('BLOG_MAIN_ID', '')

# ── 인수 파싱 ──────────────────────────────────────────────────
if len(sys.argv) < 3:
    print('사용법: py scripts\\fix_add_keep_reading.py <검색키워드> <카테고리A|B|C|D>')
    print('예시:   py scripts\\fix_add_keep_reading.py "memory care" A')
    sys.exit(1)

search_query = sys.argv[1]
category_key = sys.argv[2].upper()

# ── 1. 글 검색 ────────────────────────────────────────────────
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

print(f'검색: "{search_query}" (카테고리 {category_key})')

results = service.posts().search(
    blogId=BLOG_ID,
    q=search_query,
    fetchBodies=False,
).execute()

items = results.get('items', [])
if not items:
    print('글을 찾지 못했습니다.')
    sys.exit(1)

# 검색 결과 표시
print(f'\n검색 결과 {len(items)}건:')
for i, item in enumerate(items[:5]):
    print(f'  [{i}] {item["id"]} — {item["title"]}')

choice = input('\n몇 번째 글을 수정하시겠습니까? (0부터): ').strip()
try:
    chosen = items[int(choice)]
except (ValueError, IndexError):
    print('잘못된 입력')
    sys.exit(1)

post_id = chosen['id']
print(f'\n선택: {chosen["title"]}')

# ── 2. 본문 가져오기 ──────────────────────────────────────────
post    = service.posts().get(blogId=BLOG_ID, postId=post_id, view='AUTHOR').execute()
title   = post['title']
content = post['content']
print(f'본문 길이: {len(content)} chars')

# ── 3. Keep Reading 이미 있는지 확인 ─────────────────────────
if 'Keep Reading' in content or '📖' in content:
    print('\n✅ Keep Reading 섹션 이미 존재 — 수정 불필요')
    sys.exit(0)

# ── 4. Keep Reading 생성 ──────────────────────────────────────
related_html = add_internal_links(
    category_key=category_key,
    current_title=title,
)

if not related_html:
    print(f'\n⚠️  카테고리 {category_key} 발행 글 없음 — Keep Reading 추가 불가')
    sys.exit(1)

print(f'\nKeep Reading 섹션 생성 완료')

# ── 5. 면책 문구 <hr> 앞에 삽입 ──────────────────────────────
soup = BeautifulSoup(content, 'html.parser')
hr   = soup.find('hr')

if hr:
    hr.insert_before(BeautifulSoup(related_html, 'html.parser'))
    print('삽입 위치: 면책 문구 <hr> 앞')
else:
    soup.append(BeautifulSoup(related_html, 'html.parser'))
    print('삽입 위치: 본문 끝 (hr 없음)')

fixed_content = str(soup)

# ── 6. Blogger 반영 ───────────────────────────────────────────
confirm = input('\nBlogger에 반영하시겠습니까? (y/n): ').strip().lower()
if confirm != 'y':
    print('취소됨')
    sys.exit(0)

result = service.posts().patch(
    blogId=BLOG_ID,
    postId=post_id,
    body={'content': fixed_content}
).execute()

print(f'\n✅ 완료: {result.get("url")}')
