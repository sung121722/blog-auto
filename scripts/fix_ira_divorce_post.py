"""
fix_ira_divorce_post.py
"How to Split an IRA in Divorce After Retirement Without Taxes" 글 수정
개인참조 2회 → 1회 (두 번째 "In one case I saw" 제거)
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

# ── 1. 제목으로 글 검색 ─────────────────────────────────────────
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

TARGET_TITLE = 'How to Split an IRA in Divorce After Retirement Without Taxes'

print(f'검색 중: "{TARGET_TITLE}"')

# Blogger search API
results = service.posts().search(
    blogId=BLOG_ID,
    q='IRA Divorce Retirement Taxes',
    fetchBodies=False,
).execute()

post_id = None
for item in results.get('items', []):
    if TARGET_TITLE.lower() in item.get('title', '').lower():
        post_id = item['id']
        print(f'✅ 발견: [{item["id"]}] {item["title"]}')
        break

if not post_id:
    print('글을 찾지 못했습니다. 수동으로 POST_ID를 입력하세요.')
    print('사용법: POST_ID = "여기에ID입력" 로 수정 후 재실행')
    sys.exit(1)

# ── 2. 본문 가져오기 ───────────────────────────────────────────
post    = service.posts().get(blogId=BLOG_ID, postId=post_id, view='AUTHOR').execute()
title   = post['title']
content = post['content']

print(f'\n제목: {title}')
print(f'본문 길이: {len(content)} chars')

# ── 3. 개인참조 탐지 ──────────────────────────────────────────
PERSONAL_RE = re.compile(
    r'\b(i\s+watched|i\s+saw|i\s+know|i\s+once|i\s+always|i\s+remember'
    r'|i\s+tried|i\s+learned|i\'ve|i\s+retired|when\s+i\s|i\s+helped'
    r'|i\s+spent|i\s+worked|i\'ve\s+sat)\b',
    re.IGNORECASE
)

text = BeautifulSoup(content, 'html.parser').get_text()
matches = [(m.start(), m.group(), text[max(0,m.start()-60):m.end()+80]) for m in PERSONAL_RE.finditer(text)]

print(f'\n개인참조 표현 {len(matches)}곳:')
for pos, phrase, ctx in matches:
    print(f'  [{phrase}] ...{ctx.strip()}...')
    print()

if len(matches) <= 1:
    print('✅ 개인참조 1회 이하 — 수정 불필요')
    sys.exit(0)

# ── 4. 자동 수정 ──────────────────────────────────────────────
def auto_fix(html: str) -> str:
    """
    두 번째 이후 개인참조 → 무인칭/3인칭으로 교체.
    첫 번째("I watched a colleague at 67")만 유지.
    """
    soup = BeautifulSoup(html, 'html.parser')

    replacements = [
        # 두 번째 개인참조: "In one case I saw" → "In one documented case"
        (re.compile(r'\bIn one case I saw\b', re.IGNORECASE),
         'In one documented case'),
        # "I saw that" 형태
        (re.compile(r'\b(when I saw|as I saw)\b', re.IGNORECASE),
         'as reported'),
        # 혹시 남아있을 "I know" 형태
        (re.compile(r'\bI know\b', re.IGNORECASE),
         'You probably know'),
        # "I've seen" (첫 번째 "I watched" 이후에만 발동)
        (re.compile(r"\bI've seen\b", re.IGNORECASE),
         'Many advisors have seen'),
    ]

    first_kept = False  # 첫 번째 개인참조("I watched") 보존 플래그

    for tag in soup.find_all(string=True):
        raw = str(tag)
        if not raw.strip():
            continue

        new_text = raw

        # 첫 번째 "I watched"는 건드리지 않음
        if not first_kept and re.search(r'\bI watched\b', raw, re.IGNORECASE):
            first_kept = True
            continue  # 이 노드는 수정 없이 통과

        # 나머지 노드에 replacements 적용
        for pattern, repl in replacements:
            new_text = pattern.sub(repl, new_text)

        if new_text != raw:
            tag.replace_with(BeautifulSoup(new_text, 'html.parser'))

    return str(soup)


fixed_content = auto_fix(content)

# ── 5. 수정 전/후 비교 ────────────────────────────────────────
orig_count  = len(PERSONAL_RE.findall(text))
fixed_text  = BeautifulSoup(fixed_content, 'html.parser').get_text()
fixed_count = len(PERSONAL_RE.findall(fixed_text))
print(f'수정 전: {orig_count}개 → 수정 후: {fixed_count}개')

if fixed_count > 1:
    print('⚠️  자동 수정 후에도 2개 이상 — 수동 확인 필요')
    # 남은 위치 출력
    for m in PERSONAL_RE.finditer(fixed_text):
        ctx = fixed_text[max(0,m.start()-60):m.end()+80]
        print(f'  [{m.group()}] ...{ctx.strip()}...')
    sys.exit(1)

# ── 6. Blogger API 업데이트 ───────────────────────────────────
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
