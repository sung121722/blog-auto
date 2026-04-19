# senior_config.py
# Today's Senior TV - High-Value Category Config

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
}

WEEKDAY_CATEGORY_MAP = {
    0: "A",  # Mon: Medicare
    1: "B",  # Tue: Retirement
    2: "C",  # Wed: Aging in Place
    3: "A",  # Thu: Medicare
    4: "B",  # Fri: Retirement
    5: "C",  # Sat: Aging in Place
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
        "how to compare medicare advantage plans 2025",
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
    ],
    "B": [
        "how to protect retirement savings from inflation 2025",
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
        "best states for retirement tax benefits 2025",
        "required minimum distribution rules after 73",
        "how to leave money to grandchildren tax free",
        "annuity vs 401k which is better for retirement income",
        "senior financial advisor vs robo advisor which to choose",
    ],
    "C": [
        "best stair lifts for seniors home reviews 2025",
        "walk-in bathtub vs walk-in shower for elderly",
        "how to make bathroom safer for elderly parents",
        "grab bars installation cost for senior bathroom",
        "best wheelchair ramp for home entrance reviews",
        "aging in place home modifications cost guide",
        "best smart home devices to help elderly live alone",
        "best medical alert systems for seniors living alone",
        "life alert vs bay alarm medical comparison review",
        "best fall detection devices for elderly 2025",
        "best ergonomic chairs for seniors with back pain",
        "top rated raised toilet seats for elderly safety",
        "best non-slip floor mats for elderly bathroom",
        "senior-friendly kitchen gadgets for arthritic hands",
        "best hearing aids for seniors on medicare 2025",
    ],
}

def get_keywords_for_category(category_key: str, n: int = 4) -> list:
    pool = KEYWORDS.get(category_key, [])
    return random.sample(pool, min(n, len(pool)))


# ─────────────────────────────────────────
# NOSTALGIA HOOKS
# ─────────────────────────────────────────
NOSTALGIA_HOOKS = [
    {"era": "1970s", "topic": "classic muscle cars",
     "hook": "Remember cruising down Main Street in your '69 Mustang or '70 Chevelle, windows down, 8-track blasting?",
     "image_query": "1969 Ford Mustang classic car vintage americana"},
    {"era": "1970s", "topic": "drive-in theaters",
     "hook": "Saturday nights at the drive-in — a double feature, a bag of popcorn, and the whole family piled into the station wagon.",
     "image_query": "1970s drive-in theater vintage americana"},
    {"era": "1970s", "topic": "disco era and bell-bottoms",
     "hook": "Bell-bottoms, platform shoes, and the Bee Gees playing from every radio.",
     "image_query": "1970s disco era fashion vintage"},
    {"era": "1980s", "topic": "Saturday morning cartoons",
     "hook": "Saturday mornings meant one thing: a bowl of cereal and hours of cartoons before your parents woke up.",
     "image_query": "1980s saturday morning cartoons vintage television"},
    {"era": "1980s", "topic": "family road trips",
     "hook": "No GPS, no cell phones — just a paper map, a cooler full of sodas, and the open road.",
     "image_query": "1980s family road trip station wagon americana"},
    {"era": "1970s", "topic": "neighborhood block parties",
     "hook": "When neighbors were neighbors — block parties where everyone brought a dish and the kids ran wild until dark.",
     "image_query": "1970s neighborhood block party americana vintage"},
    {"era": "1980s", "topic": "classic rock and cassette tapes",
     "hook": "Rewinding a cassette tape with a pencil, waiting for your favorite song and hitting record at just the right moment.",
     "image_query": "1980s cassette tape walkman classic rock vintage"},
    {"era": "1970s", "topic": "soda fountains and diners",
     "hook": "Sliding into a booth at the local diner, ordering a chocolate malt and a burger for under two dollars.",
     "image_query": "1970s american diner soda fountain vintage"},
    {"era": "1960s", "topic": "family Sunday dinners",
     "hook": "Sunday dinner at grandma's — pot roast, homemade pie, and every cousin you had crammed around one table.",
     "image_query": "1960s american family dinner table vintage"},
    {"era": "1970s", "topic": "little league and backyard games",
     "hook": "We played until the streetlights came on. That was the rule. Nobody had to tell us twice.",
     "image_query": "1970s children playing outside neighborhood vintage"},
]

def get_random_nostalgia_hook() -> dict:
    return random.choice(NOSTALGIA_HOOKS)


# ─────────────────────────────────────────
# TRANSITION BRIDGES
# ─────────────────────────────────────────
BRIDGES = {
    "A": [
        "Just like we used to carefully read every line of a car insurance policy, navigating Medicare plans today takes that same sharp eye — and the stakes are even higher.",
        "We took care of what mattered most back then. Today, making sure you have the right Medicare coverage is how you take care of yourself.",
        "Back then, we knew every neighbor on the block. Now, knowing your Medicare options can make that same difference in your daily life.",
    ],
    "B": [
        "We worked hard for every dollar in those days. The question now is: is your retirement nest egg protected the way it deserves to be?",
        "Just like we tuned up our cars every few thousand miles, your retirement plan needs a regular check-up too.",
        "We built things to last back then. Your retirement savings deserve the same lasting protection.",
    ],
    "C": [
        "We made our homes a castle back then — and now, making sure that home is safe and comfortable is the most important project you'll tackle.",
        "Just like we poured weekends into making the house feel just right, today's seniors are redesigning their homes to age in place — safely and on their own terms.",
        "Home meant everything. With the right modifications, it still can.",
    ],
}

def get_bridge_for_category(category_key: str) -> str:
    options = BRIDGES.get(category_key, ["Times change, but good planning never goes out of style."])
    return random.choice(options)


PUBLISH_LABELS_BASE = ["Senior Life", "Baby Boomers", "Today's Senior TV"]

def get_post_labels(category_key: str) -> list:
    cat = CATEGORIES[category_key]
    return PUBLISH_LABELS_BASE + [cat["label"]]
