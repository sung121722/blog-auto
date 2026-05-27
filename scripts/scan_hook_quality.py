"""
scan_hook_quality.py — 발행 글 첫 단락 품질 스캔
노스탤지아 오프닝 / 얇은 콘텐츠 / 주제 불일치 감지
"""
import sys, json, re, time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

import requests as _req
from bs4 import BeautifulSoup

# ── 감지 패턴 ─────────────────────────────────────────────────

# 노스탤지아/무관 오프닝 패턴
NOSTALGIA_RE = re.compile(
    r'^.{0,300}(?:'
    r'remember those|remember when|back in the \d{4}|those were the days'
    r'|saturday evening|sunday afternoon|summer of \d{4}'
    r'|growing up|as a kid|when i was young|my (mother|father|grandfather|grandmother)'
    r'|the smell of|the sound of|the taste of'
    r')',
    re.IGNORECASE | re.DOTALL
)

# 목표와 무관한 오프닝 (재정/건강 주제 글인데 음식/파티/어린시절 이야기로 시작)
OFF_TOPIC_RE = re.compile(
    r'\b(block party|potato salad|baseball|apple pie|lincoln logs|tinker toys'
    r'|erector set|sparkler|fourth of july|thanksgiving dinner'
    r'|neighborhood kids|front porch|screen door)\b',
    re.IGNORECASE
)

def fetch_article(url: str) -> tuple[str, str, int]:
    """(first_300_chars, full_text, word_count) 반환"""
    try:
        r = _req.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')

        # 본문 추출 (사이드바 제외)
        article = (soup.find('div', class_='post-body')
                   or soup.find('article')
                   or soup.find('div', class_='entry-content'))
        if not article:
            return '', '', 0

        text = article.get_text(' ', strip=True)
        word_count = len(text.split())
        first_300 = text[:300]
        return first_300, text, word_count
    except Exception as e:
        return f'ERROR:{e}', '', 0

# ── 발행 이력 로드 ────────────────────────────────────────────
published_dir = Path('data/published')
records = []
for p in sorted(published_dir.glob('*.json')):
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        if d.get('url'):
            records.append(d)
    except:
        pass

print(f'총 {len(records)}개 글 스캔 시작...\n')

issues = []
for i, rec in enumerate(records):
    url   = rec['url']
    title = rec.get('title', '')[:60]
    cat   = rec.get('category_key', '?')

    first_300, full_text, wc = fetch_article(url)

    if first_300.startswith('ERROR'):
        print(f'[{i+1:02d}] SKIP  {title[:50]}')
        time.sleep(0.5)
        continue

    found = []

    # 노스탤지아 오프닝 체크
    if NOSTALGIA_RE.search(first_300):
        found.append('노스탤지아오프닝')

    # 무관 단어 오프닝 체크
    if OFF_TOPIC_RE.search(first_300):
        found.append('주제무관오프닝')

    # 단어수 체크 (Category별)
    min_wc = 750 if cat in ('C', 'D') else 900
    if wc < min_wc:
        found.append(f'얇은콘텐츠({wc}단어)')
    elif wc < 1100:
        found.append(f'짧은콘텐츠({wc}단어)')

    status = '⚠️  ' + ' + '.join(found) if found else '✅'
    print(f'[{i+1:02d}] {status:<40} [{cat}] {title[:50]}')

    if found:
        issues.append({
            'url': url,
            'title': title,
            'issues': found,
            'category': cat,
            'word_count': wc,
            'first_300': first_300[:200],
        })

    time.sleep(0.8)

print(f'\n{"="*70}')
print(f'문제 있는 글: {len(issues)}개 / 전체 {len(records)}개')

if issues:
    print()
    for item in issues:
        print(f'  [{item["category"]}] {item["title"]}')
        print(f'       URL: {item["url"]}')
        print(f'       문제: {", ".join(item["issues"])}')
        if item.get("first_300"):
            print(f'       첫 문장: {item["first_300"][:120]}...')
        print()

    out = Path('data/hook_issues.json')
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'결과 저장: {out}')
