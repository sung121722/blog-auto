"""
fix_beneficiary_v2.py
"How to Update Beneficiaries on Retirement Accounts in 2026" 글 수정
1. Keep Reading 자기 자신 링크 제거
2. "I can't emphasize this enough" → 무인칭으로 교체
"""
import sys, re
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

from bots.publisher_bot import get_google_credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import os

BLOG_ID = os.getenv('BLOG_MAIN_ID', '')

# ── 1. 글 찾기 ────────────────────────────────────────────────
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

TARGET_TITLE = 'How to Update Beneficiaries on Retirement Accounts in 2026'

print(f'검색 중: "{TARGET_TITLE}"')

results = service.posts().search(
    blogId=BLOG_ID,
    q='Update Beneficiaries Retirement Accounts 2026',
    fetchBodies=False,
).execute()

post_id = None
for item in results.get('items', []):
    if 'beneficiar' in item.get('title', '').lower():
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

# ── 3. 버그 진단 ──────────────────────────────────────────────
soup = BeautifulSoup(content, 'html.parser')

# BUG 1: Keep Reading 자기 자신 링크
self_links = []
for a in soup.find_all('a'):
    if title.lower()[:30] in a.get_text().lower():
        parent_div = a.find_parent('div')
        is_keep_reading = parent_div and 'Keep Reading' in (parent_div.get_text() or '')
        if is_keep_reading:
            self_links.append(a)
            print(f'\n[BUG1] 자기 자신 링크 발견: {a.get_text()[:60]}')

# BUG 2: "I can't emphasize"
ICANT_RE = re.compile(r"I can'?t emphasize", re.IGNORECASE)
text_plain = soup.get_text()
icant_matches = ICANT_RE.findall(text_plain)
print(f'\n[BUG2] "I can\'t emphasize" 발견: {len(icant_matches)}건')

if not self_links and not icant_matches:
    print('\n✅ 수정할 버그 없음')
    sys.exit(0)

# ── 4. 자동 수정 ──────────────────────────────────────────────
print('\n수정 시작...')

# BUG 1 수정: Keep Reading에서 자기 자신 링크 li 태그 제거
for a in self_links:
    li = a.find_parent('li')
    if li:
        li.decompose()
        print(f'  [BUG1 수정] 자기 자신 li 태그 제거')

# BUG 2 수정: 텍스트 노드에서 "I can't emphasize this enough" → 무인칭
for tag in soup.find_all(string=True):
    raw = str(tag)
    if ICANT_RE.search(raw):
        fixed = ICANT_RE.sub("This point cannot be emphasized enough", raw)
        tag.replace_with(BeautifulSoup(fixed, 'html.parser'))
        print(f'  [BUG2 수정] "I can\'t emphasize" → "This point cannot be emphasized enough"')

fixed_content = str(soup)

# ── 5. 결과 확인 ──────────────────────────────────────────────
fixed_soup = BeautifulSoup(fixed_content, 'html.parser')
remaining_self = [a for a in fixed_soup.find_all('a')
                  if title.lower()[:30] in a.get_text().lower()]
remaining_icant = ICANT_RE.findall(fixed_soup.get_text())

print(f'\n수정 후 자기링크: {len(remaining_self)}개 (이전: {len(self_links)}개)')
print(f'수정 후 I can\'t: {len(remaining_icant)}개 (이전: {len(icant_matches)}개)')

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

print(f'\n✅ 수정 완료: {result.get("url")}')
