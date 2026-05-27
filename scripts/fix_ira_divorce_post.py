"""
fix_ira_divorce_post.py
"How to Split an IRA in Divorce After Retirement Without Taxes" 글 수정
1. "In one case I saw" → "In one documented case" (개인참조 2회 → 1회)
2. Keep Reading 섹션 추가 (동일 카테고리 B 글 3개)
"""
import sys, re, json, random
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
TARGET_TITLE = 'How to Split an IRA in Divorce After Retirement Without Taxes'

# ── 1. 글 찾기 ────────────────────────────────────────────────
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

print(f'검색 중: "{TARGET_TITLE}"')

results = service.posts().search(
    blogId=BLOG_ID,
    q='IRA Divorce Retirement Split Taxes',
    fetchBodies=False,
).execute()

post_id = None
for item in results.get('items', []):
    if 'ira' in item.get('title', '').lower() and 'divorce' in item.get('title', '').lower():
        post_id = item['id']
        print(f'✅ 발견: [{item["id"]}] {item["title"]}')
        break

if not post_id:
    print('글을 찾지 못했습니다.')
    sys.exit(1)

# ── 2. 본문 가져오기 ──────────────────────────────────────────
post    = service.posts().get(blogId=BLOG_ID, postId=post_id, view='AUTHOR').execute()
title   = post['title']
content = post['content']
print(f'\n제목: {title}')
print(f'본문 길이: {len(content)} chars')

soup = BeautifulSoup(content, 'html.parser')
plain = soup.get_text()

# ── 3. 버그 진단 ──────────────────────────────────────────────
ISAWRE = re.compile(r'\bIn one case I saw\b', re.IGNORECASE)
isawm  = ISAWRE.findall(plain)
print(f'\n[BUG1] "In one case I saw": {len(isawm)}건')

# Keep Reading 섹션 존재 여부
has_keep_reading = '📖 Keep Reading' in plain or 'Keep Reading' in plain
print(f'[BUG2] Keep Reading 섹션: {"있음 ✅" if has_keep_reading else "없음 ❌"}')

if not isawm and has_keep_reading:
    print('\n✅ 수정할 버그 없음')
    sys.exit(0)

fixes_applied = []

# ── 4. BUG1 수정: "In one case I saw" → 무인칭 ────────────────
if isawm:
    for tag in soup.find_all(string=True):
        raw = str(tag)
        if ISAWRE.search(raw):
            fixed = ISAWRE.sub('In one documented case', raw)
            tag.replace_with(BeautifulSoup(fixed, 'html.parser'))
            print(f'  [BUG1 수정] "In one case I saw" → "In one documented case"')
    fixes_applied.append('개인참조 2번째 제거')

# ── 5. BUG2: Keep Reading 섹션 추가 ──────────────────────────
if not has_keep_reading:
    related_html = add_internal_links(
        category_key='B',
        current_title=title,
    )
    if related_html:
        # 면책 문구 <hr> 직전에 삽입
        disclaimer_hr = soup.find('hr')
        if disclaimer_hr:
            disclaimer_hr.insert_before(BeautifulSoup(related_html, 'html.parser'))
            print(f'  [BUG2 수정] Keep Reading 섹션 추가 (면책 문구 앞)')
        else:
            # fallback: 맨 끝에 추가
            soup.append(BeautifulSoup(related_html, 'html.parser'))
            print(f'  [BUG2 수정] Keep Reading 섹션 추가 (본문 끝)')
        fixes_applied.append('Keep Reading 섹션 추가')
    else:
        print('  [BUG2] 동일 카테고리 발행 글 없음 — Keep Reading 추가 불가')

fixed_content = str(soup)

# ── 6. 결과 확인 ──────────────────────────────────────────────
fixed_plain = BeautifulSoup(fixed_content, 'html.parser').get_text()
print(f'\n수정 전 "In one case I saw": {len(isawm)}건 → 수정 후: {len(ISAWRE.findall(fixed_plain))}건')
print(f'수정 적용: {fixes_applied}')

# ── 7. Blogger 반영 ───────────────────────────────────────────
confirm = input('\nBlogger에 반영하시겠습니까? (y/n): ').strip().lower()
if confirm != 'y':
    print('취소됨')
    sys.exit(0)

result = service.posts().patch(
    blogId=BLOG_ID,
    postId=post_id,
    body={'content': fixed_content}
).execute()

print(f'\n✅ 수정 완료: {result.get("url")}')
