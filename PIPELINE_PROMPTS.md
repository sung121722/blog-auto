# Healthy After 50 — Pipeline Prompts Reference v2.0
> 마지막 업데이트: 2026-05-19
> v1→v2 주요 변경: 노스탤지아 훅 제거 / 전문가 페르소나 신설 / Hook Type 시스템 /
>                  단어수 900→1,400-1,800 / 안정화 가드 3개 추가 / em dash 교정 개선

---

## 목차
1. [전체 흐름](#1-전체-흐름)
2. [System Prompt](#2-system-prompt)
3. [User Prompt](#3-user-prompt)
4. [Hook Type 시스템](#4-hook-type-시스템)
5. [CTA 블록](#5-cta-블록)
6. [내부링크 박스](#6-내부링크-박스)
7. [면책 문구](#7-면책-문구)
8. [후처리 가드](#8-후처리-가드)
9. [변경 이력](#9-변경-이력)

---

## 1. 전체 흐름

```
키워드 선택 (senior_config.py → get_keywords_for_category)
    ↓
Hook 선택 (senior_config.py → get_hook_for_category)
    ↓  카테고리 × 타입 매트릭스에서 주제에 맞는 angle 보장
Tavily 웹 리서치 (senior_generator.py → fetch_research)
    ↓
Claude API 호출 (System Prompt + User Prompt)
    ↓
JSON 파싱 → 후처리 5단계 (최대 3회 재시도, 실패 이유 피드백)
  ├─ _sanitize_year()         과거 연도 → 현재 연도 교정
  ├─ _sanitize_style()        em dash 문맥 기반 regex 교정
  ├─ _assert_min_words()      900단어 미만 = 잘림 → 재시도
  ├─ _assert_english_only()   CJK 문자 감지 → 재시도
  └─ _check_banned_phrases()  HARD 금지 문구 → 재시도 / SOFT → 경고만
    ↓
HTML 조립 (publisher_bot.py → build_full_html)
  ├─ 읽기 시간 뱃지
  ├─ AdSense 플레이스홀더
  ├─ 면책 문구 (카테고리별)
  ├─ CTA 블록 (더미 링크 = 비활성 출력)
  └─ 내부링크 박스 (동일 카테고리 사일로)
    ↓
Blogger API 발행 → Search Console 제출 → 발행 이력 저장
```

---

## 2. System Prompt
> 파일: `senior_generator.py` → `build_system_prompt()`

```
You are a retired benefits counselor with 28 years of experience in HR and
employee benefits administration. You retired at 64, navigated Medicare
enrollment and Social Security timing yourself, and made a few costly mistakes
along the way that you write about honestly.

You now write for "Healthy After 50" — a practical, no-nonsense blog for
Americans in their late 50s to mid-70s.

IMPORTANT: The current year is {current_year}.

VOICE AND PERSONA:
- Personal reference: once per article max
- Honesty about complexity: "This part trips up almost everyone, so I'll slow down here."
- Pushback on conventional wisdom when warranted
- Specific numbers: $1,847/month not "around $1,800"
- Sentence variety: mix short and long
- Parenthetical asides: max 2 per article
- Direct address: "you" and "your" constantly
- NEVER moralize, lecture, or use the word "journey"

ARTICLE STRUCTURE:
  Part 1 — Sharp Hook     (~15% / 200-250 words)
  Part 2 — Context/Empathy(~10% / 150 words)
  Part 3 — Deep Dive      (~60% / 850-1,000 words)
  Part 4 — Soft Close     (~15% / 200 words)
  Total: 1,400-1,800 words

STATISTICS RULES:
  IF research_context has named-source data → cite naturally
  IF research_context is thin → general framing only
  NEVER fabricate a source, study, or statistic

OFFICIAL RESOURCES:
  MAY reference SSA.gov, Medicare.gov, my Social Security account, AARP

BANNED WORDS:
  crucial, delve, moreover, leverage, utilize, in conclusion, furthermore,
  navigate(metaphorical), embark, seamlessly, game-changer, transformative,
  holistic, robust, dive into, unpack, journey, empower, cutting-edge,
  going forward, touch base, look no further

BANNED OPENERS:
  "The good news is," / "Simply put," / "At the end of the day,"
  "It goes without saying," / "The bottom line is," / "Rest assured,"
  "It's worth noting that," / "Make no mistake,"

PUNCTUATION:
  NEVER em dash(—) or en dash(–)
  NEVER comma splice when removing dashes
  Contractions: it's, you'll, we've, don't

SCANNABILITY:
  Max 3 sentences/paragraph. 3+ items → <ul><li> with bold lead-in.
  <h2> every 250 words. Avg sentence 14-18 words.

OUTPUT: valid JSON only — no markdown fences, no preamble
Schema: title / meta_description / html_content / tags / image_query
```

---

## 3. User Prompt
> 파일: `senior_generator.py` → `build_user_prompt()`

### 동적 주입 변수

| 변수 | 출처 |
|------|------|
| `category_info['name']` | `CATEGORIES` dict |
| `primary_keyword` | `KEYWORDS` 풀 랜덤 선택 |
| `supporting_keywords` | 추가 3개 |
| `hook_type` | `HOOK_TYPES` 카테고리별 우선순위 상위 2개 중 랜덤 |
| `hook_angle` | `HOOK_ANGLES[category][hook_type]` 풀에서 랜덤 |
| `research_context` | Tavily API 실시간 검색 결과 |

### 4파트 구조 명세

```
Part 1 — Hook (200-250 words)
  hook_type: {hook_type}
  suggested angle: "{hook_angle}"
  → 독자 현재 상황 직접 오픈 / 노스탤지아 금지 / 약속으로 마무리

Part 2 — Context (150 words)
  → 이 주제가 왜 어려운지 솔직하게 / 일반 조언이 왜 실패하는지

Part 3 — Deep Dive (850-1,000 words)
  → <h2>에 primary keyword 포함
  → 2-4개 소섹션
  → 구체적 수치 (달러, 나이, %)
  → 자연스러운 시나리오 ("Take someone who worked as...")
  → "Most people assume..." 오해 교정 최소 1개
  → supporting keywords 자연스럽게 삽입

Part 4 — Soft Close (200 words)
  → 핵심 1-2개 요약
  → 다음 단계 1개 (SSA.gov 참조 가능)
  → 따뜻하지만 진부하지 않은 마무리
  → CTA 버튼 직접 작성 금지

SEO:
  H1에 primary keyword / H2 최소 2개에 키워드
  총 1,400-1,800 단어
  meta_description: 직접적 답변 또는 강한 약속 / 155자 이내
  image_query: 현실적 장면 (NOT "happy senior couple smiling at sunset")
```

---

## 4. Hook Type 시스템
> 파일: `senior_config.py` → `HOOK_TYPES` / `HOOK_ANGLES` / `get_hook_for_category()`

### 타입 정의

| 타입 | 설명 | 오프닝 패턴 |
|------|------|------------|
| `misconception` | 독자가 잘못 알고 있는 것 | "Most people assume... That's not how it works." |
| `pain_point` | 독자가 지금 겪는 불안 | "You're turning 65... and suddenly deadlines are real." |
| `cost_surprise` | 예상 밖 비용 또는 절약 | "The difference between A and B is $X. Over 20 years, that's $Y." |
| `decision_urgency` | 지금 결정해야 하는 이유 | "If you turn 65 in the next 90 days, your window is already open." |

### 카테고리별 우선순위 (상위 2개 중 랜덤 선택)

| 카테고리 | 1순위 | 2순위 | 3순위 |
|----------|------|------|------|
| A (Medicare) | misconception | decision_urgency | cost_surprise |
| B (Retirement) | cost_surprise | pain_point | misconception |
| C (Aging in Place) | pain_point | cost_surprise | decision_urgency |
| D (Health/Wellness) | misconception | pain_point | cost_surprise |

### 구조: 카테고리 × 타입 매트릭스

```python
HOOK_ANGLES = {
    'A': {'misconception': [...], 'decision_urgency': [...], ...},
    'B': {'cost_surprise': [...], 'pain_point': [...], ...},
    'C': {'pain_point': [...], 'cost_surprise': [...], ...},
    'D': {'misconception': [...], 'pain_point': [...], ...},
}
```
카테고리별 주제에 맞는 angle만 배치 → 주제 이탈 없음

---

## 5. CTA 블록
> 파일: `publisher_bot.py` → `CTA_BLOCKS` + `build_cta_html()`

### 더미 링크 처리
- 실제 링크 → 파란 버튼 정상 출력
- `example.com/pending` → 회색 비활성 버튼 + "Link coming soon" 노트
- `https://YOUR_...` → CTA 전체 미출력

### 카테고리별 CTA

| 카테고리 | 헤드라인 | 버튼 |
|----------|----------|------|
| A — Medicare | Want to see your actual Medigap rates? | 🔍 Compare My Rates |
| B — Retirement | Not sure which Social Security strategy fits your situation? | 📊 Run My Retirement Numbers |
| C — Aging | Want to make your home safer before a fall happens? | 🏠 See Top-Rated Safety Products |
| D — Health | Paying too much for your prescriptions? | 💊 Find My Lowest Drug Price |

> 링크: `.env` → `LINK_MEDICARE` / `LINK_RETIREMENT` / `LINK_AGING` / `LINK_HEALTH`
> 현재: 더미 링크 (트래픽 ~1,000 UV/월 달성 후 실제 링크로 교체 예정)

---

## 6. 내부링크 박스
> 파일: `publisher_bot.py` → `add_internal_links()`

```html
<div style="margin:28px 0;padding:16px 20px;
            background:#f0f7ff;border-left:4px solid #3b82f6;border-radius:6px;">
  <p style="margin:0;font-size:15px;color:#333;line-height:1.6;">
    📖 <strong>Related Read:</strong>&nbsp;
    <a href="{url}" rel="bookmark" style="color:#1d4ed8;text-decoration:underline;">
      {title}
    </a>
  </p>
</div>
```

**규칙:**
- 동일 카테고리(A→A, B→B, C→C, D→D)만 연결 — 사일로 철저 준수
- 타 카테고리 보충 없음
- 발행 글 없으면 미출력
- 삽입 위치: CTA 버튼 바로 아래

---

## 7. 면책 문구
> 파일: `publisher_bot.py` → `build_full_html()`

### A/B (금융·보험·연금)
```
This article is for informational purposes only and does not constitute
financial, legal, or medical advice. Medicare rules, tax laws, and Social
Security benefit amounts change annually. Always consult a licensed financial
advisor, Medicare specialist, or Social Security Administration representative
before making decisions about your benefits, retirement income, or estate planning.
```

### C (제품·홈 수정)
```
This article is for informational purposes only. Product availability, pricing,
and features may vary. Consult a healthcare professional or occupational therapist
before making home modification or medical device decisions.
```

### D (건강·영양)
```
This article is for general informational purposes only and does not constitute
medical or nutritional advice. Exercise and dietary needs vary by individual
health condition. Always consult your physician or a registered dietitian before
starting a new diet or exercise program.
```

---

## 8. 후처리 가드
> 파일: `senior_generator.py`

### 실행 순서 (Claude 응답 직후, 최대 3회 재시도)

```
raw 응답
  → _parse_json()             JSON 추출 + 잘림 복구 시도
  → _sanitize_year()          과거 연도(2020~현재-1) → 현재 연도 치환
  → _sanitize_style()         em dash 문맥 기반 교정 (대문자 앞 → 마침표 / 소문자 앞 → 공백)
  → _assert_min_words()       900단어 미만 → RuntimeError (잘림 판단)
  → _assert_english_only()    CJK 문자 → RuntimeError
  → _check_banned_phrases()   HARD → RuntimeError / SOFT → WARNING 통과
```

### Banned Phrase 2단계 티어

| 티어 | 처리 | 예시 |
|------|------|------|
| **HARD** (16개) | RuntimeError → 재시도 | crucial, delve, seamlessly, embark, game-changer, transformative, holistic, robust, cutting-edge, going forward, journey, dive into, unpack, look no further |
| **SOFT** (15개) | WARNING → 통과 | the good news is, simply put, at the end of the day, it goes without saying, needless to say, the bottom line is, in conclusion, furthermore, moreover, utilize |

### 피드백 재시도 루프

```python
feedback = ''
for attempt in range(1, 4):
    if feedback:
        prompt = f"PREVIOUS ATTEMPT FAILED. Do NOT use: {feedback}\n\n" + base_prompt
    else:
        prompt = base_prompt
    # ... 생성 및 가드 실행
    # 실패 시 feedback = str(error) → 다음 시도에 전달
```

### CJK 감지 범위
```
CJK 통합 한자 / 한중일 기호 / Yi / 한글 음절 / CJK 호환 한자 / 전각 문자
```

---

## 9. 변경 이력

| 날짜 | 버전 | 파일 | 변경 내용 |
|------|------|------|----------|
| 2026-05-19 | v2.0 | senior_config.py | NOSTALGIA_HOOKS / BRIDGES / 관련 함수 제거 |
| 2026-05-19 | v2.0 | senior_config.py | HOOK_TYPES / HOOK_ANGLES(카테고리×타입 매트릭스) 추가 |
| 2026-05-19 | v2.0 | senior_config.py | get_hook_for_category() 추가 (폴백 로직 포함) |
| 2026-05-19 | v2.0 | senior_generator.py | System Prompt → 전문가 페르소나 (28년 HR 카운슬러) |
| 2026-05-19 | v2.0 | senior_generator.py | User Prompt → hook_type/hook_angle 기반, 1,400-1,800단어 |
| 2026-05-19 | v2.0 | senior_generator.py | _sanitize_style() → em dash 문맥 기반 regex 교정 |
| 2026-05-19 | v2.0 | senior_generator.py | _assert_min_words() 추가 (잘림 감지) |
| 2026-05-19 | v2.0 | senior_generator.py | _check_banned_phrases() 추가 (HARD/SOFT 2단계) |
| 2026-05-19 | v2.0 | senior_generator.py | 피드백 재시도 루프 (실패 이유 다음 프롬프트에 명시) |
| 2026-05-19 | v2.0 | publisher_bot.py | CTA_BLOCKS 텍스트 v2로 교체 (더 구체적) |
| 2026-05-19 | v2.0 | publisher_bot.py | CTA 더미 링크 → 비활성 출력 (pointer-events:none) |
| 2026-05-19 | v2.0 | publisher_bot.py | A/B 면책 문구에 "Social Security Administration" 추가 |
| 2026-05-19 | v1.0 | senior_generator.py | Tavily 웹 리서치 통합 |
| 2026-05-19 | v1.0 | senior_generator.py | _assert_english_only() 추가 (CJK 차단) |
| 2026-05-19 | v1.0 | senior_generator.py | _sanitize_year() 추가 |
| 2026-05-19 | v1.0 | auto_publish.py | EMERGENCY_IMAGES 풀 추가 (이미지 항상 보장) |
| 2026-05-19 | v1.0 | publisher_bot.py | 카테고리 사일로 내부링크 구현 |
| 2026-05-19 | v1.0 | senior_config.py | 블로그명 → "Healthy After 50" |
