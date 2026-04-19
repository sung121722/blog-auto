# senior_collector.py
# 키워드 수집 및 중복 방지 (60일 이력 관리)

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from senior_config import KEYWORDS, CATEGORIES, get_category_for_today

HISTORY_FILE = Path(__file__).parent / 'data' / 'keyword_history.json'
MAX_HISTORY_DAYS = 60


def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_history(history: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_used_keywords() -> set:
    history = load_history()
    cutoff = datetime.now() - timedelta(days=MAX_HISTORY_DAYS)
    return {kw for kw, meta in history.items()
            if datetime.fromisoformat(meta['used_at']) > cutoff}


def pick_fresh_keywords(category_key: str, n: int = 4) -> list:
    used = get_used_keywords()
    pool = KEYWORDS.get(category_key, [])
    fresh = [kw for kw in pool if kw not in used]
    if len(fresh) < n:
        fresh = pool  # 모두 소진 시 리셋
    return random.sample(fresh, min(n, len(fresh)))


def collect_keywords_for_today() -> dict:
    category_key, category_info = get_category_for_today()
    keywords = pick_fresh_keywords(category_key, n=4)
    keywords.sort(key=lambda k: len(k), reverse=True)  # 롱테일 우선
    return {
        'category_key': category_key,
        'category_info': category_info,
        'primary_keyword': keywords[0],
        'supporting_keywords': keywords[1:],
    }


def mark_keyword_used(keyword: str, category_key: str):
    history = load_history()
    history[keyword] = {'used_at': datetime.now().isoformat(), 'category': category_key}
    save_history(history)
