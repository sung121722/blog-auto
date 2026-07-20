# senior_collector.py
# 키워드 수집 및 중복 방지 (60일 이력 관리)
# Hook 앵글 이력 추적 (30일 — 같은 앵글 재사용 방지)

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from senior_config import KEYWORDS, CATEGORIES, get_category_for_today

HISTORY_FILE    = Path(__file__).parent / 'data' / 'keyword_history.json'
HOOK_HIST_FILE  = Path(__file__).parent / 'data' / 'hook_history.json'
OPENING_HIST_FILE = Path(__file__).parent / 'data' / 'opening_history.json'
MAX_HISTORY_DAYS     = 60
HOOK_COOLDOWN_DAYS   = 30   # 같은 앵글이 30일 이내 재사용되면 제외
OPENING_HISTORY_KEEP = 8    # 프롬프트에 주입할 최근 오프닝 개수


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


def pick_fresh_keywords(category_key: str, n: int = 4, exclude: set | None = None) -> list:
    used = get_used_keywords() | (exclude or set())
    pool = KEYWORDS.get(category_key, [])
    fresh = [kw for kw in pool if kw not in used]
    if len(fresh) < n:
        # 60일 이력 기준으로 다 소진됨 — exclude만 제외하고, 가장 오래 전에 쓴 키워드들 중에서만 재선택
        candidates = [kw for kw in pool if kw not in (exclude or set())] or pool
        history = load_history()
        candidates.sort(key=lambda kw: history.get(kw, {}).get('used_at', ''))  # 없거나 오래된 것 우선
        fresh = candidates[:max(n * 2, n)]
    return random.sample(fresh, min(n, len(fresh)))


def collect_keywords_for_today(category_key: str | None = None, exclude_primary: set | None = None) -> dict:
    """category_key 지정 시 오늘의 카테고리 대신 사용 (재시도 시 동일 카테고리 유지용).
    exclude_primary 지정 시 해당 키워드들은 primary/supporting 후보에서 제외 (중복 재시도용)."""
    if category_key is None:
        category_key, category_info = get_category_for_today()
    else:
        from senior_config import CATEGORIES
        category_info = CATEGORIES[category_key]
    keywords = pick_fresh_keywords(category_key, n=4, exclude=exclude_primary)
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


# ─── Hook 앵글 이력 ──────────────────────────────────────────────

def load_hook_history() -> dict:
    """hook_history.json 로드. 구조: {angle_text: {used_at, category, hook_type}}"""
    if HOOK_HIST_FILE.exists():
        with open(HOOK_HIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_hook_history(history: dict):
    HOOK_HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HOOK_HIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_used_hook_angles(cooldown_days: int = HOOK_COOLDOWN_DAYS) -> set:
    """쿨다운 기간 내 사용된 hook angle 집합 반환"""
    history = load_hook_history()
    cutoff = datetime.now() - timedelta(days=cooldown_days)
    return {
        angle for angle, meta in history.items()
        if datetime.fromisoformat(meta['used_at']) > cutoff
    }


def mark_hook_used(hook_angle: str, hook_type: str, category_key: str):
    """발행 완료 후 호출 — hook angle을 이력에 기록"""
    history = load_hook_history()
    history[hook_angle] = {
        'used_at': datetime.now().isoformat(),
        'category': category_key,
        'hook_type': hook_type,
    }
    # 오래된 이력 정리 (90일 초과)
    cutoff = datetime.now() - timedelta(days=90)
    history = {
        a: m for a, m in history.items()
        if datetime.fromisoformat(m['used_at']) > cutoff
    }
    save_hook_history(history)


# ─── 오프닝 문장 이력 (템플릿 반복 방지) ──────────────────────────────

def get_recent_openings(n: int = OPENING_HISTORY_KEEP) -> list:
    """가장 최근 발행된 글들의 오프닝 첫 문장 목록 반환 (최신순)"""
    if not OPENING_HIST_FILE.exists():
        return []
    with open(OPENING_HIST_FILE, 'r', encoding='utf-8') as f:
        history = json.load(f)
    return history[-n:][::-1]


def mark_opening_used(opening_text: str):
    """발행 완료 후 호출 — 오프닝 첫 문장을 이력에 추가 (최근 OPENING_HISTORY_KEEP*3개만 보관)"""
    history = []
    if OPENING_HIST_FILE.exists():
        with open(OPENING_HIST_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    history.append(opening_text)
    history = history[-(OPENING_HISTORY_KEEP * 3):]
    OPENING_HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENING_HIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
