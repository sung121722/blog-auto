"""
quality_compare.py — Claude vs Gemini 품질 비교 테스트

동일 키워드로 양쪽 모델을 각 1회 호출해 결과를 나란히 비교.
출력: quality_compare_YYYYMMDD.json + 콘솔 요약

사용법:
    python scripts/quality_compare.py --category C
    python scripts/quality_compare.py --category D
"""
import sys, os, json, re, argparse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'bots'))
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from bots.engine_loader import EngineLoader, ClaudeWriter, GeminiWriter
from senior_config import CATEGORIES, get_keywords_for_category, get_hook_for_category
from senior_generator import (
    build_system_prompt, build_user_prompt,
    _parse_json, _sanitize_year, _sanitize_style
)

BANNED_HARD = {
    'crucial', 'delve', 'seamlessly', 'embark', 'game-changer',
    'game changer', 'transformative', 'holistic', 'robust',
    'cutting-edge', 'cutting edge', 'going forward', 'journey',
    'dive into', 'unpack', 'look no further',
}


def word_count(html: str) -> int:
    return len(BeautifulSoup(html, 'html.parser').get_text().split())


def has_specific_numbers(html: str) -> bool:
    """$X,XXX 형태 구체적 금액 포함 여부 (반올림된 $X,000 제외)"""
    text = BeautifulSoup(html, 'html.parser').get_text()
    specific = re.findall(r'\$\d{1,3}(?:,\d{3})+', text)
    round_nums = [n for n in specific if re.match(r'\$\d+,000$', n)]
    return len(specific) > len(round_nums)


def persona_score(html: str) -> dict:
    """페르소나 지표 점수 계산"""
    text = BeautifulSoup(html, 'html.parser').get_text().lower()
    scores = {}
    # 직접 주소 ("you", "your")
    scores['direct_address'] = min(text.count(' you ') + text.count(' your '), 30)
    # 개인 경험 참조 (1회 권장)
    scores['personal_ref'] = int(bool(re.search(r'\b(i |my |when i |i\'ve |i\'d )', text)))
    # 구체적 달러 금액
    scores['specific_dollars'] = int(has_specific_numbers(html))
    # Most people assume... 패턴
    scores['correction_pattern'] = int(bool(re.search(r'most people (assume|think|believe)', text)))
    # 친근한 어조 지표
    scores['contractions'] = int(bool(re.search(r"\b(it's|you'll|don't|that's|you'd|we've)\b", text)))
    return scores


def banned_count(html: str) -> list:
    text = html.lower()
    return [p for p in BANNED_HARD if p in text]


def analyze(model_name: str, raw: str) -> dict:
    try:
        data = _parse_json(raw)
        data = _sanitize_year(data)
        data = _sanitize_style(data)
        html = data.get('html_content', '')
        wc = word_count(html)
        banned = banned_count(html)
        persona = persona_score(html)
        return {
            'model': model_name,
            'success': True,
            'title': data.get('title', '')[:80],
            'word_count': wc,
            'banned_hard': banned,
            'banned_hard_count': len(banned),
            'persona_score': persona,
            'persona_total': sum(persona.values()),
            'has_specific_numbers': persona['specific_dollars'],
            'response_length': len(raw),
            'html_preview': html[:400],
        }
    except Exception as e:
        return {
            'model': model_name,
            'success': False,
            'error': str(e),
            'response_length': len(raw),
        }


def run_comparison(category_key: str):
    cat_info = CATEGORIES[category_key]
    keywords = get_keywords_for_category(category_key, n=4)
    hook     = get_hook_for_category(category_key)

    word_target = '1,100-1,400 words' if category_key in ('C', 'D') else '1,400-1,800 words'
    deep_dive   = '650-800 words'     if category_key in ('C', 'D') else '850-1,000 words'

    system_prompt = build_system_prompt(category_key=category_key)
    user_prompt   = build_user_prompt(
        category_key, cat_info, keywords[0], keywords[1:],
        hook['hook_type'], hook['hook_angle'],
        word_target=word_target, deep_dive=deep_dive,
    )

    print(f'\n{"="*60}')
    print(f'Quality Compare: Category {category_key} ({cat_info["name"]})')
    print(f'Keyword: {keywords[0]}')
    print(f'{"="*60}')

    results = []

    # ── Claude ──────────────────────────────────────────────
    loader = EngineLoader()
    all_opts = loader._config.get('writing', {}).get('options', {})

    claude_writer = ClaudeWriter(all_opts.get('claude', {}))
    if claude_writer.api_key:
        print('\n[1/2] Calling Claude Sonnet...')
        raw_claude = claude_writer.write(user_prompt, system=system_prompt)
        results.append(analyze('claude-sonnet', raw_claude))
        print(f'  Done ({len(raw_claude)} chars)')
    else:
        print('[1/2] Claude: ANTHROPIC_API_KEY not set — skipping')

    # ── Gemini ──────────────────────────────────────────────
    gemini_writer = GeminiWriter(all_opts.get('gemini', {}))
    if gemini_writer.api_key:
        print('[2/2] Calling Gemini 2.5 Flash...')
        raw_gemini = gemini_writer.write(user_prompt, system=system_prompt)
        results.append(analyze('gemini-2.5-flash', raw_gemini))
        print(f'  Done ({len(raw_gemini)} chars)')
    else:
        print('[2/2] Gemini: GEMINI_API_KEY not set — skipping')

    if not results:
        print('No results — check API keys in .env')
        return

    # ── Summary ─────────────────────────────────────────────
    print(f'\n{"─"*60}')
    print('COMPARISON SUMMARY')
    print(f'{"─"*60}')
    headers = ['Metric', 'Claude Sonnet', 'Gemini 2.5 Flash']
    rows = []
    claude_r = next((r for r in results if 'claude' in r['model']), None)
    gemini_r = next((r for r in results if 'gemini' in r['model']), None)

    def fmt(r, key):
        if not r:
            return 'N/A'
        return str(r.get(key, 'N/A'))

    metrics = [
        ('Success',            'success'),
        ('Word Count',         'word_count'),
        ('Banned Hard Phrases','banned_hard_count'),
        ('Banned Phrases',     'banned_hard'),
        ('Persona Score /7',   'persona_total'),
        ('Specific $$ numbers','has_specific_numbers'),
        ('Response Length',    'response_length'),
    ]
    for label, key in metrics:
        print(f'  {label:<25} Claude: {fmt(claude_r, key):<20} Gemini: {fmt(gemini_r, key)}')

    if claude_r and claude_r.get('success'):
        print(f'\nClaude title:  {claude_r["title"]}')
    if gemini_r and gemini_r.get('success'):
        print(f'Gemini title:  {gemini_r["title"]}')

    # ── Save ────────────────────────────────────────────────
    out_dir  = Path(__file__).parent.parent / 'data'
    out_dir.mkdir(exist_ok=True)
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = out_dir / f'quality_compare_{category_key}_{ts}.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'category': category_key,
            'keyword':  keywords[0],
            'ts':       ts,
            'results':  results,
        }, f, ensure_ascii=False, indent=2)
    print(f'\nFull results saved: {out_path.name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', default='C', choices=['A','B','C','D'])
    args = parser.parse_args()
    run_comparison(args.category)
