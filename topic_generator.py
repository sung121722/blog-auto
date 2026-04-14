"""
topic_generator.py
Blogger 노스탤지어 블로그용 주제를 AI로 자동 생성하여
config/creative_dna.json의 topic_pool에 추가합니다.

사용법:
  python topic_generator.py           # 기본 20개 생성
  python topic_generator.py --count 50
  python topic_generator.py --category "School Days" --count 10
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / '.env')

BASE_DIR = Path(__file__).parent
DNA_PATH = BASE_DIR / 'config' / 'creative_dna.json'

CATEGORIES = [
    "School Days",
    "Teen Years & Coming of Age",
    "Food & Taste Memories",
    "Toys, Games & Play",
    "Pop Culture & Entertainment",
    "Holidays & Seasons",
    "Neighborhood Life",
    "Work, Fashion & Americana",
]

SYSTEM_PROMPT = (
    "You are a creative director for a senior nostalgia blog targeting American Baby Boomers "
    "and Gen X readers (ages 50-80). "
    "Your job is to generate specific, vivid, memory-triggering blog topic ideas. "
    "Each topic should feel like a real memory — not a generic concept. "
    "Think: a specific object, place, smell, TV show, food, or moment from the 1950s–1980s. "
    "Output ONLY a JSON array. No explanation, no markdown, no extra text."
)


def build_prompt(category: str, count: int, existing_topics: list[str]) -> str:
    existing_sample = "\n".join(f"- {t}" for t in existing_topics[-20:])
    return f"""Generate {count} unique blog topic ideas for the category: "{category}"

Each topic must:
- Be specific and sensory (mention a real object, place, era, or experience)
- Sound like something a 68-year-old American would say to an old friend
- NOT duplicate or closely resemble these existing topics:
{existing_sample}

Return ONLY a JSON array of strings. Example:
["Topic one here", "Topic two here", "Topic three here"]
"""


def load_dna() -> dict:
    with open(DNA_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_dna(data: dict):
    with open(DNA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_topics(category: str, count: int, existing_topics: list[str]) -> list[str]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = build_prompt(category, count, existing_topics)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # JSON 파싱
    try:
        topics = json.loads(raw)
        if isinstance(topics, list):
            return [t.strip() for t in topics if isinstance(t, str) and t.strip()]
    except json.JSONDecodeError:
        # 마크다운 코드블록 제거 후 재시도
        import re
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            topics = json.loads(match.group())
            return [t.strip() for t in topics if isinstance(t, str) and t.strip()]

    print(f"[WARN] 파싱 실패. 원본:\n{raw[:300]}")
    return []


def run(category: str | None, count: int):
    dna = load_dna()
    pool = dna.get('topic_pool', [])
    existing_set = {item['topic'].lower() for item in pool}

    categories = [category] if category else CATEGORIES
    per_category = max(1, count // len(categories))

    added = 0
    for cat in categories:
        existing_in_cat = [item['topic'] for item in pool if item.get('category') == cat]
        print(f"\n[{cat}] 생성 중... (목표: {per_category}개)")

        try:
            new_topics = generate_topics(cat, per_category, existing_in_cat)
        except Exception as e:
            print(f"  [ERROR] {e}")
            continue

        for topic in new_topics:
            if topic.lower() in existing_set:
                print(f"  [SKIP] 중복: {topic[:60]}")
                continue
            pool.append({"category": cat, "topic": topic})
            existing_set.add(topic.lower())
            added += 1
            print(f"  [+] {topic[:80]}")

    dna['topic_pool'] = pool
    save_dna(dna)
    print(f"\n완료: {added}개 추가 (총 {len(pool)}개)")


def main():
    parser = argparse.ArgumentParser(description='Blogger 노스탤지어 주제 자동 생성')
    parser.add_argument('--count', type=int, default=20, help='생성할 주제 수 (기본: 20)')
    parser.add_argument('--category', type=str, default=None,
                        help=f'특정 카테고리만 생성. 선택지: {", ".join(CATEGORIES)}')
    args = parser.parse_args()

    if args.category and args.category not in CATEGORIES:
        print(f"[ERROR] 알 수 없는 카테고리: {args.category}")
        print(f"선택 가능: {', '.join(CATEGORIES)}")
        sys.exit(1)

    run(category=args.category, count=args.count)


if __name__ == '__main__':
    main()
