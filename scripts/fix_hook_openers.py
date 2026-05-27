"""
fix_hook_openers.py — 노스탤지아 오프닝 / 얇은 콘텐츠 일괄 수정
data/hook_issues.json 읽어서:
  - 노스탤지아오프닝: Claude API로 첫 단락 교체
  - 얇은콘텐츠(<900단어): Blogger Draft 전환
"""
import sys, json, re, os
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path('.env'))

from bots.publisher_bot import get_google_credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import anthropic

BLOG_ID = os.getenv('BLOG_MAIN_ID', '')

# ── 설정 ──────────────────────────────────────────────────────
DRY_RUN = '--dry-run' in sys.argv   # 실제 변경 없이 미리보기만

# ── 데이터 로드 ───────────────────────────────────────────────
issues_path = Path('data/hook_issues.json')
if not issues_path.exists():
    print('data/hook_issues.json 없음 — 먼저 scan_hook_quality.py 실행')
    sys.exit(1)

issues = json.loads(issues_path.read_text(encoding='utf-8'))
print(f'수정 대상: {len(issues)}개 글\n')

# 카테고리별 분류
nostalgia = [x for x in issues if '노스탤지아오프닝' in x['issues']
                                or '주제무관오프닝' in x['issues']]
thin      = [x for x in issues if any('얇은콘텐츠' in iss for iss in x['issues'])
                                and '노스탤지아오프닝' not in x['issues']
                                and '주제무관오프닝' not in x['issues']]
both      = [x for x in issues if ('노스탤지아오프닝' in x['issues']
                                   or '주제무관오프닝' in x['issues'])
                                and any('얇은콘텐츠' in iss for iss in x['issues'])]

print(f'  노스탤지아 오프닝만: {len(nostalgia)}개 → 첫 단락 교체')
print(f'  얇은 콘텐츠만:       {len(thin)}개 → Draft 전환')
print(f'  복합 문제:           {len(both)}개 → Draft 전환 (재생성 대기)')
print()

if DRY_RUN:
    print('[DRY RUN 모드 — 실제 변경 없음]\n')

# ── Claude API 클라이언트 ─────────────────────────────────────
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))

def rewrite_intro(title: str, old_intro: str) -> str:
    """Claude Haiku로 첫 단락을 키워드 중심으로 교체"""
    prompt = f"""You are rewriting the opening paragraph of a blog post for seniors.

Article title: "{title}"

The current opening is off-topic or nostalgic:
"{old_intro[:300]}"

Write a NEW opening paragraph (2-3 sentences, ~60-80 words) that:
1. Opens with the reader's exact concern or anxiety related to the title
2. Makes the reader feel understood immediately
3. Ends with a clear promise of what this article delivers
4. Uses "you" and "your" — NOT "I" or "we"
5. NO nostalgic stories, NO "In today's world", NO rhetorical questions

Return ONLY the new paragraph text, no labels or explanations."""

    msg = client.messages.create(
        model='claude-haiku-4-5',
        max_tokens=200,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return msg.content[0].text.strip()

# ── Blogger API ───────────────────────────────────────────────
creds   = get_google_credentials()
service = build('blogger', 'v3', credentials=creds)

results = {'fixed_intro': [], 'drafted': [], 'failed': []}

# ── 1. 노스탤지아 오프닝 → 첫 단락 교체 ─────────────────────
print('='*60)
print('① 노스탤지아 오프닝 수정')
print('='*60)

for item in nostalgia:
    title    = item['title']
    post_id  = item.get('post_id', '')
    url      = item['url']

    print(f'\n  [{title[:55]}]')
    print(f'  현재 첫문장: {item["first_sentence"][:80]}...')

    if not post_id:
        print('  ⚠️  post_id 없음 — 스킵')
        results['failed'].append(item)
        continue

    try:
        # 본문 가져오기
        post    = service.posts().get(blogId=BLOG_ID, postId=post_id, view='AUTHOR').execute()
        content = post['content']
        soup    = BeautifulSoup(content, 'html.parser')

        # 첫 번째 <p> 태그 찾기
        first_p = soup.find('p')
        if not first_p:
            print('  ⚠️  첫 <p> 태그 없음 — 스킵')
            results['failed'].append(item)
            continue

        old_text = first_p.get_text()

        # Claude로 새 오프닝 생성
        new_intro = rewrite_intro(title, old_text)
        print(f'  새 첫문장: {new_intro[:80]}...')

        if not DRY_RUN:
            first_p.replace_with(BeautifulSoup(f'<p>{new_intro}</p>', 'html.parser'))
            service.posts().patch(
                blogId=BLOG_ID,
                postId=post_id,
                body={'content': str(soup)}
            ).execute()
            print(f'  ✅ 수정 완료')
        else:
            print(f'  [DRY RUN] 수정 예정')

        results['fixed_intro'].append(title)

    except Exception as e:
        print(f'  ❌ 오류: {e}')
        results['failed'].append(item)

# ── 2. 얇은 콘텐츠 + 복합 문제 → Draft 전환 ─────────────────
print('\n' + '='*60)
print('② 얇은 콘텐츠 / 복합 문제 → Draft 전환')
print('='*60)

for item in thin + both:
    title   = item['title']
    post_id = item.get('post_id', '')
    wc      = item.get('word_count', 0)

    print(f'\n  [{title[:55]}] ({wc}단어)')

    if not post_id:
        print('  ⚠️  post_id 없음 — 스킵')
        results['failed'].append(item)
        continue

    try:
        if not DRY_RUN:
            service.posts().revert(blogId=BLOG_ID, postId=post_id).execute()
            print(f'  ✅ Draft 전환 완료')
        else:
            print(f'  [DRY RUN] Draft 전환 예정')

        results['drafted'].append(title)

    except Exception as e:
        print(f'  ❌ 오류: {e}')
        results['failed'].append(item)

# ── 결과 요약 ─────────────────────────────────────────────────
print('\n' + '='*60)
print('결과 요약')
print('='*60)
print(f'  첫 단락 교체: {len(results["fixed_intro"])}개')
print(f'  Draft 전환:   {len(results["drafted"])}개')
print(f'  실패:         {len(results["failed"])}개')

if results['drafted']:
    print('\n📋 Draft 전환된 글 (재생성 필요):')
    for t in results['drafted']:
        print(f'  - {t}')

# 결과 저장
out = Path('data/fix_results.json')
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n결과 저장: {out}')
