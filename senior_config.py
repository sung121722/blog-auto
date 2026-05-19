# senior_config.py
# Healthy After 50 - High-Value Category Config

import os
import random
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / '.env')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY', '')

# ─────────────────────────────────────────
# HIGH-VALUE CATEGORIES
# ─────────────────────────────────────────
CATEGORIES = {
    "A": {
        "name": "Medicare & Senior Living",
        "slug": "medicare-senior-living",
        "label": "Medicare & Insurance",
        "adsense_cpc_tier": "ultra-high",
    },
    "B": {
        "name": "Retirement & Estate Planning",
        "slug": "retirement-estate-planning",
        "label": "Retirement Finance",
        "adsense_cpc_tier": "ultra-high",
    },
    "C": {
        "name": "Aging in Place",
        "slug": "aging-in-place",
        "label": "Home & Safety",
        "adsense_cpc_tier": "high",
    },
    "D": {
        "name": "Senior Health & Wellness",
        "slug": "senior-health-wellness",
        "label": "Health & Fitness",
        "adsense_cpc_tier": "medium",
    },
}

WEEKDAY_CATEGORY_MAP = {
    0: "A",  # Mon: Medicare      (ultra-high CPC)
    1: "B",  # Tue: Retirement    (ultra-high CPC)
    2: "D",  # Wed: Health        (medium CPC, 공유율↑)
    3: "A",  # Thu: Medicare      (ultra-high CPC)
    4: "B",  # Fri: Retirement    (ultra-high CPC)
    5: "C",  # Sat: Aging in Place(high CPC)
    6: "D",  # Sun: Health        (medium CPC, 주말 건강 검색↑)
}

def get_category_for_today():
    from datetime import datetime
    weekday = datetime.now().weekday()
    key = WEEKDAY_CATEGORY_MAP.get(weekday, random.choice(list(CATEGORIES.keys())))
    return key, CATEGORIES[key]


# ─────────────────────────────────────────
# HIGH-CPC KEYWORD POOLS
# ─────────────────────────────────────────
KEYWORDS = {
    "A": [
        "best medicare supplement plans for seniors over 70",
        "how to compare medicare advantage plans 2026",
        "medicare part d prescription drug coverage explained",
        "medicare vs medicaid difference for low income seniors",
        "best medicare plan for retired federal employees",
        "does medicare cover dental and vision for seniors",
        "how to switch medicare supplement plans without penalty",
        "medicare supplement plan G vs plan N comparison",
        "how much does assisted living cost per month",
        "best assisted living facilities in the united states",
        "signs your parent needs memory care vs assisted living",
        "how to pay for nursing home without going broke",
        "continuing care retirement community cost and benefits",
        "independent living vs assisted living which is better",
        "how to qualify for medicaid for nursing home care",
        "senior living options for low income retirees",
        # 롱테일 추가
        "what does medicare supplement plan g cover in 2026",
        "does medicare cover home health care after hospital stay",
        "how to appeal a medicare claim denial step by step",
        "medicare advantage vs original medicare which is better for retirees",
        "what is the medicare donut hole and how to avoid it",
        "does medicare cover cataract surgery for seniors",
        "how to choose between medicare hmo and ppo plans",
        "how long does medicare cover skilled nursing facility care",
        "does medicare pay for hearing aids for seniors 2026",
        "medicare coverage for physical therapy after knee replacement",
        "how to get extra help with medicare part d costs",
        "what happens to medicare if you move to another state",
        "can you have both medicare and employer insurance at 65",
        "best medicare supplement plans for people with diabetes",
        "how to find a medicare certified home health agency",
        "does medicare cover mental health therapy for seniors",
    ],
    "B": [
        "how to protect retirement savings from inflation 2026",
        "best way to roll over 401k to ira after retirement",
        "reverse mortgage pros and cons for seniors over 65",
        "how does a reverse mortgage work step by step",
        "how to avoid estate tax and protect inheritance",
        "best retirement income strategies for baby boomers",
        "when should you take social security benefits early",
        "roth conversion ladder strategy for retirees",
        "how to set up a living trust to avoid probate",
        "difference between will and living trust for seniors",
        "how to protect assets from nursing home costs",
        "best states for retirement tax benefits 2026",
        "required minimum distribution rules after 73",
        "how to leave money to grandchildren tax free",
        "annuity vs 401k which is better for retirement income",
        "senior financial advisor vs robo advisor which to choose",
        # 롱테일 추가
        "how much social security will i get if i retire at 62",
        "what is the best age to claim social security benefits",
        "how to reduce taxes on social security benefits",
        "what happens to my 401k if the stock market crashes",
        "how to create a retirement budget that actually works",
        "spousal social security benefits for non-working spouse",
        "how to split ira in divorce after retirement",
        "what is a power of attorney and why seniors need one",
        "how to update beneficiaries on retirement accounts",
        "what to do with inherited ira from parent rules 2026",
        "how to avoid probate without a trust for seniors",
        "best way to give money to grandchildren without taxes",
        "how does inflation affect fixed income retirees",
        "catch up contribution rules for 401k over 50 in 2026",
        "what is a qualified longevity annuity contract qlac",
        "how to use home equity to fund retirement without selling",
    ],
    "C": [
        "best stair lifts for seniors home reviews 2026",
        "walk-in bathtub vs walk-in shower for elderly",
        "how to make bathroom safer for elderly parents",
        "grab bars installation cost for senior bathroom",
        "best wheelchair ramp for home entrance reviews",
        "aging in place home modifications cost guide",
        "best smart home devices to help elderly live alone",
        "best medical alert systems for seniors living alone",
        "life alert vs bay alarm medical comparison review",
        "best fall detection devices for elderly 2026",
        "best ergonomic chairs for seniors with back pain",
        "top rated raised toilet seats for elderly safety",
        "best non-slip floor mats for elderly bathroom",
        "senior-friendly kitchen gadgets for arthritic hands",
        "best hearing aids for seniors on medicare 2026",
        # 롱테일 추가
        "how to prevent falls at home for elderly parents",
        "best lighting for seniors to prevent falls at night",
        "how to childproof a home for elderly parents with dementia",
        "voice activated devices for seniors with limited mobility",
        "best video doorbells for seniors living alone",
        "how to set up emergency contact system for elderly parent",
        "best adjustable beds for seniors with back problems",
        "how to organize medications for elderly parent at home",
        "best large button phones for seniors with poor vision",
        "home modifications for seniors with parkinson disease",
        "best shower chairs and benches for elderly safety",
        "how to help aging parent stay home instead of nursing home",
        "best gps trackers for seniors with dementia wandering",
        "how to make a bedroom safer for elderly parent",
        "best robotic vacuums for seniors with limited mobility",
        "caregiver burnout signs and how to cope as adult child",
    ],
    "D": [
        # 식단 / 영양
        "best diet for seniors over 70 to stay healthy",
        "anti-inflammatory foods for seniors with arthritis",
        "how much protein do seniors need per day",
        "best vitamins and supplements for seniors over 65",
        "foods to avoid for seniors with high blood pressure",
        "mediterranean diet benefits for seniors over 60",
        "best foods for seniors to prevent memory loss",
        "how to eat healthy on a fixed income as a senior",
        "best calcium rich foods for seniors to prevent osteoporosis",
        "soft foods for seniors with difficulty swallowing",
        "how to boost energy levels in seniors through diet",
        "best diet for seniors with type 2 diabetes",
        "foods that help seniors sleep better at night",
        "how to stay hydrated as a senior tips and tricks",
        "best meal delivery services for seniors at home",
        "healthy snacks for seniors with diabetes",
        # 운동 / 피트니스
        "best low impact exercises for seniors over 65",
        "chair exercises for seniors with limited mobility",
        "how much exercise do seniors need per week",
        "best balance exercises for seniors to prevent falls",
        "yoga for seniors beginners guide at home",
        "water aerobics benefits for seniors with joint pain",
        "strength training for seniors over 70 beginners",
        "best walking shoes for seniors with foot problems",
        "how to start exercising after 65 safely",
        "tai chi for seniors benefits and beginner moves",
        "stretching exercises for seniors with tight muscles",
        "best exercise bikes for seniors at home 2026",
        "how to stay motivated to exercise as a senior",
        "swimming benefits for seniors with arthritis",
        "best fitness tracker for seniors with heart conditions",
        "exercise tips for seniors recovering from hip replacement",
    ],
}

def get_keywords_for_category(category_key: str, n: int = 4) -> list:
    """키워드 반환 — 구버전 연도(현재연도-1 이하) 자동 교정 후 반환"""
    from datetime import datetime
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    current_year = datetime.now().year
    pool = KEYWORDS.get(category_key, [])

    # 강제 연도 교정: 현재연도보다 낮은 연도 → 현재연도로 자동 치환
    corrected = []
    for kw in pool:
        original = kw
        for past_year in range(2020, current_year):
            if str(past_year) in kw:
                kw = kw.replace(str(past_year), str(current_year))
                _logger.warning(f'[YEAR GUARD] 키워드 연도 자동교정: "{original}" → "{kw}"')
        corrected.append(kw)

    return random.sample(corrected, min(n, len(corrected)))


# ─────────────────────────────────────────
# HOOK TYPE SYSTEM (v2.0 — nostalgia 대체)
# ─────────────────────────────────────────
# 4가지 훅 타입: 독자가 지금 겪는 상황 직접 공략
#   misconception   — 독자가 잘못 알고 있는 것
#   pain_point      — 독자가 지금 겪는 구체적 불안
#   cost_surprise   — 예상 밖의 비용 또는 절약 정보
#   decision_urgency— 지금 결정해야 하는 이유
# ─────────────────────────────────────────

# 카테고리별 훅 타입 우선순위 (앞 2개 중 랜덤 선택)
HOOK_TYPES = {
    'A': ['misconception', 'decision_urgency', 'cost_surprise'],
    'B': ['cost_surprise', 'pain_point', 'misconception'],
    'C': ['pain_point', 'cost_surprise', 'decision_urgency'],
    'D': ['misconception', 'pain_point', 'cost_surprise'],
}

# 카테고리 × 훅타입 매트릭스 (카테고리별 주제에 맞는 angle만 배치)
HOOK_ANGLES = {
    'A': {  # Medicare & Senior Living
        'misconception': [
            "Most people assume they can sign up for Medicare any time after 65. That's not how it works, and the penalty for getting it wrong follows you permanently.",
            "Most people think Plan G is always the best Medicare supplement. For some people, Plan N saves real money every year.",
            "Most people believe Medicare covers everything once they turn 65. The gaps in coverage are where the expensive surprises happen.",
            "Most people assume their employer coverage automatically coordinates with Medicare at 65. It doesn't always work that way.",
            "Most people assume Medicare Advantage and Original Medicare are basically the same thing with different names. The differences matter a lot when you get sick.",
        ],
        'decision_urgency': [
            "If you turn 65 in the next 90 days, your Medicare Initial Enrollment Period is already open. Missing it has consequences that last years.",
            "Medicare Open Enrollment runs October 15 through December 7 every year. If you've never compared your Part D plan against current options, this window matters.",
            "If you're retiring before 65 and losing employer coverage, you have a 60-day Special Enrollment Period. After that, you wait for General Enrollment, and you'll pay a penalty.",
            "If you've been on a Medicare Advantage plan for more than a year and haven't compared it during Open Enrollment, you may be paying for coverage that no longer fits your doctors or medications.",
        ],
        'cost_surprise': [
            "The difference between Medicare Supplement Plan G and Plan N is about $40 a month in premiums. Whether that's worth it depends entirely on how often you see specialists.",
            "Medicare's late enrollment penalty for Part B is 10% added to your premium for every 12-month period you were eligible but didn't enroll. That penalty is permanent.",
            "A three-day hospital stay can cost Medicare beneficiaries over $1,600 out of pocket under Original Medicare with no supplement plan.",
            "The Medicare Part D coverage gap still creates unexpected costs for people on expensive brand-name medications, even after the donut hole technically closed.",
        ],
        'pain_point': [
            "You're turning 65 in a few months, you're still working, and suddenly Medicare enrollment deadlines are real. Most HR departments don't warn you until it's almost too late.",
            "You've been getting Medicare Advantage plan change notices every fall, and you're not sure if your doctors are still covered.",
            "Your Medicare Part D premium just went up again, and you're not sure if you're still on the best plan for your specific medications.",
            "You signed up for Medicare Advantage three years ago because the premium was low. Now you're dealing with prior authorization delays and out-of-network costs that weren't obvious at enrollment.",
        ],
    },
    'B': {  # Retirement & Estate Planning
        'cost_surprise': [
            "The difference between claiming Social Security at 62 versus 70 is roughly $700 to $900 a month, depending on your earnings history. Over 20 years, that gap compounds significantly.",
            "Required minimum distributions from a traditional IRA can push retirees into a higher tax bracket if not planned for in advance.",
            "A reverse mortgage origination fee can run between $2,500 and $6,000. Most people don't ask about it until after they're already interested.",
            "If you inherit an IRA from a parent, the SECURE Act rules give you 10 years to withdraw the money, not a lifetime. The tax implications can be substantial.",
        ],
        'pain_point': [
            "You've worked for decades building a retirement nest egg, and now inflation is quietly eroding what it will actually buy.",
            "You're trying to figure out when to claim Social Security, and everyone you ask gives you a different answer.",
            "You have a parent who needs care, and you're realizing their assets may not last as long as their needs.",
            "You've got money in a traditional IRA, a 401k from a previous job, and maybe a small pension. Figuring out how to turn that into reliable monthly income is more complicated than anyone told you.",
        ],
        'misconception': [
            "Most people assume waiting until 70 to claim Social Security is always the right move. The math only works if you live long enough.",
            "Most people think a will is enough to protect their estate. A will goes through probate. A trust does not.",
            "Most people assume their 401k beneficiary designation matches their will. These are separate documents, and the beneficiary form always wins.",
            "Most people think the biggest retirement risk is a market crash. Running out of money because you lived longer than you planned is statistically more common.",
        ],
        'decision_urgency': [
            "If you're within five years of retirement, the sequence of investment returns in those years matters more than almost any other single factor in your long-term outcome.",
            "The SECURE 2.0 Act changed required minimum distribution ages and catch-up contribution limits. If you haven't reviewed your strategy since 2023, some of those changes affect you directly.",
            "If you're 72 or older and haven't taken your required minimum distribution yet this year, the deadline is December 31. The penalty for missing it is 25% of the amount you should have withdrawn.",
        ],
    },
    'C': {  # Aging in Place
        'pain_point': [
            "You've watched a parent or friend have a fall at home, and now you're looking at your own house differently.",
            "You want to stay in your home as you get older, but you're starting to notice things that worry you.",
            "Your parent lives alone and you're three states away. Every unanswered phone call becomes a moment of real anxiety.",
            "You helped a parent through a fall and a hospital stay, and now you're determined to get your own home ready before something similar happens.",
        ],
        'cost_surprise': [
            "A professional home safety assessment costs between $150 and $300. A single fall resulting in a hip fracture costs the healthcare system an average of $30,000 to $40,000.",
            "Grab bar installation by a licensed contractor typically runs $200 to $500 per bar. Most people dramatically overestimate the cost and delay the decision for years.",
            "A basic medical alert system runs about $30 to $45 a month. One prevented fall that avoids an emergency room visit pays for years of service.",
            "Stair lift installation costs between $2,500 and $5,000 for a straight staircase. Moving to assisted living costs $4,000 to $6,000 a month.",
        ],
        'decision_urgency': [
            "Most home modifications for aging in place take two to four weeks to complete once scheduled. Making these decisions before a health event changes everything about the process.",
            "If a parent is being discharged from a hospital or rehab facility, you typically have 24 to 48 hours to make decisions about their living situation. Knowing the options in advance is the difference between a calm decision and a crisis decision.",
            "Fall risk increases measurably after 65 and accelerates after 75. The modifications that make a home safer are far easier to install before a fall than after one.",
        ],
        'misconception': [
            "Most falls at home don't happen in the bathroom. They happen in the bedroom, on stairs, and in the living room, where people never think to put safety equipment.",
            "Most people assume aging in place means major construction. The most effective changes are often the least expensive ones.",
            "Most people think medical alert systems are for people who've already had a health emergency. The data shows they prevent the emergency from happening in the first place.",
        ],
    },
    'D': {  # Senior Health & Wellness
        'misconception': [
            "Most people think strength training is too risky after 70. The research consistently says the opposite.",
            "Most people assume fatigue and low energy are just part of getting older. Often, they're symptoms of something addressable.",
            "Most people think the Mediterranean diet is complicated to follow. The core of it is simpler than almost any other eating pattern.",
            "Most people assume that once you have arthritis, high-impact activity is off the table. The type of activity matters more than the impact level.",
        ],
        'pain_point': [
            "You're doing everything your doctor says, but your energy levels aren't what they used to be, and you're not sure what's normal aging versus what's fixable.",
            "You're managing two or three chronic conditions and trying to figure out what you can still do to improve how you feel.",
            "You've been told to exercise more, but every time you try, something hurts. Finding a starting point that doesn't cause a setback is the real challenge.",
            "You've started taking more medications over the past few years, and you're not always sure which ones are doing what, or whether the side effects you're feeling are normal.",
        ],
        'cost_surprise': [
            "Switching Medicare Part D plans during Open Enrollment takes about 20 minutes online and can save between $200 and $600 a year on the exact same medications.",
            "Medicare's Annual Wellness Visit is covered at 100% with no copay. Most people have never used it, and it's one of the most valuable covered benefits in the program.",
            "Generic medications for common chronic conditions can cost 80 to 90 percent less than brand-name equivalents. Most people don't know they can ask for the generic by name.",
        ],
    },
}


def get_hook_for_category(category_key: str, used_angles: set = None) -> dict:
    """카테고리에 맞는 Hook Type + Angle 반환.

    카테고리별 우선순위 상위 2개 중 랜덤 선택 → 항상 주제에 맞는 angle 보장.
    used_angles 전달 시 30일 쿨다운 내 앵글 제외 → 앵글 소진 방지.
    모든 앵글이 쿨다운 중이면 가장 오래전에 쓴 앵글 선택(최소 반복 보장).
    """
    if used_angles is None:
        used_angles = set()

    type_priority = HOOK_TYPES.get(category_key, ['pain_point', 'misconception'])
    cat_angles    = HOOK_ANGLES.get(category_key, {})

    def _fresh_pool(h_type: str) -> list:
        pool = cat_angles.get(h_type, [])
        fresh = [a for a in pool if a not in used_angles]
        return fresh if fresh else pool  # 모두 소진 시 전체 풀 허용

    # 우선순위 상위 2개 타입 중 fresh angle이 있는 타입 우선 선택
    hook_type  = None
    angle_pool = []
    for h_type in type_priority[:2]:
        pool = _fresh_pool(h_type)
        if pool:
            hook_type  = h_type
            angle_pool = pool
            break

    # 모든 우선 타입 소진 → 전체 타입 순회
    if not angle_pool:
        for h_type in type_priority:
            pool = _fresh_pool(h_type)
            if pool:
                hook_type  = h_type
                angle_pool = pool
                break

    hook_angle = random.choice(angle_pool) if angle_pool else ''
    return {'hook_type': hook_type or 'pain_point', 'hook_angle': hook_angle}


PUBLISH_LABELS_BASE = ["Senior Life", "Baby Boomers", "Healthy After 50"]

def get_post_labels(category_key: str) -> list:
    cat = CATEGORIES[category_key]
    return PUBLISH_LABELS_BASE + [cat["label"]]
