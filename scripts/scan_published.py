"""
scan_published.py — 발행된 글에서 가짜 인용 패턴 스캔
Blogger API로 본문 가져와서 문제 있는 글 목록 출력
"""
import sys, json, re, time
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

import requests as _req

# ── 감지 패턴 ──────────────────────────────────────────
FAKE_CITATION = re.compile(
    r'\b(?:a |an )?20\d{2}\s+(?:study|report|research|trial)\s+'
    r'(?:from|by|at|conducted by)\s+'
    r'(?:johns?\s+hopkins?|harvard|mayo\s+clinic|stanford|cdc|nih|aarp|'
    r'university\s+of|american\s+(?:heart|college|medical))\b',
    re.IGNORECASE
)
FAKE_GUIDELINE = re.compile(
    r"cdc'?s?\s+updated\s+20\d{2}\s+guidelines?", re.IGNORECASE
)
PERSONAL_REF = re.compile(
    r'\b(i\s+tried|i\s+learned|my\s+knees|when\s+i\s|i\'ve\s|i\s+retired'
    r'|i\s+watched|i\s+saw|i\s+know|i\s+once|i\s+always|i\s+remember'
    r'|i\s+helped|i\s+spent|i\s+worked|i\'ve\s+sat)\b',
    re.IGNORECASE
)

def fetch_post_text(url: str) -> str:
    try:
        r = _req.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'html.parser')
        # 본문만 추출
        article = soup.find('article') or soup.find('div', class_='post-body') or soup
        return article.get_text(' ', strip=True)
    except Exception as e:
        return f'FETCH_ERROR: {e}'

# ── 발행 이력 로드 ──────────────────────────────────────
published_dir = Path('data/published')
records = []
for p in sorted(published_dir.glob('*.json')):
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        if d.get('url'):
            records.append(d)
    except:
        pass

print(f'URL 있는 글: {len(records)}개 스캔 시작...')
print('(글당 약 1초 소요)\n')

issues = []
for i, rec in enumerate(records):
    url = rec['url']
    title = rec.get('title', '')[:60]
    cat = rec.get('category_key', '?')

    text = fetch_post_text(url)
    if text.startswith('FETCH_ERROR'):
        print(f'[{i+1:02d}] SKIP  {title[:50]}')
        continue

    found = []
    if FAKE_CITATION.search(text):
        found.append('가짜연구인용')
    if FAKE_GUIDELINE.search(text):
        found.append('가짜가이드라인')
    # 개인참조 3회 초과
    personal_count = len(PERSONAL_REF.findall(text))
    if personal_count >= 3:
        found.append(f'개인참조{personal_count}회')

    status = '⚠️ ' + ' + '.join(found) if found else '✅'
    print(f'[{i+1:02d}] {status:<25} [{cat}] {title}')
    if found:
        issues.append({'url': url, 'title': title, 'issues': found, 'category': cat})

    time.sleep(0.8)

print(f'\n{"="*60}')
print(f'문제 있는 글: {len(issues)}개 / 전체 {len(records)}개')
if issues:
    print()
    for item in issues:
        print(f'  [{item["category"]}] {item["title"]}')
        print(f'       {item["url"]}')
        print(f'       문제: {", ".join(item["issues"])}')
        print()

    # 결과 저장
    out = Path('data/scan_issues.json')
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'결과 저장: {out}')
