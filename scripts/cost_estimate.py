import sys
sys.stdout.reconfigure(encoding='utf-8')
from senior_generator import build_system_prompt, build_user_prompt
from senior_config import CATEGORIES, get_keywords_for_category, get_hook_for_category

sys_prompt = build_system_prompt()
cat_key = 'B'
cat_info = CATEGORIES[cat_key]
kws = get_keywords_for_category(cat_key, n=4)
hook = get_hook_for_category(cat_key)

user_no_res = build_user_prompt(cat_key, cat_info, kws[0], kws[1:], hook['hook_type'], hook['hook_angle'], research_context='')
fake_research = 'SUMMARY: RMD rules changed under SECURE 2.0.\n' + ('- [Source] Content here (source: https://ssa.gov)\n' * 5)
user_with_res = build_user_prompt(cat_key, cat_info, kws[0], kws[1:], hook['hook_type'], hook['hook_angle'], research_context=fake_research)

def tok(s): return len(s) // 4

print('=== TOKEN ESTIMATES (4 chars per token) ===')
print(f'System prompt:          {len(sys_prompt):,} chars  ~{tok(sys_prompt):,} tokens')
print(f'User prompt (no res):   {len(user_no_res):,} chars  ~{tok(user_no_res):,} tokens')
print(f'User prompt (w/res):    {len(user_with_res):,} chars  ~{tok(user_with_res):,} tokens')
print(f'Total input no-res:     ~{tok(sys_prompt)+tok(user_no_res):,} tokens')
print(f'Total input with-res:   ~{tok(sys_prompt)+tok(user_with_res):,} tokens')
print()

# Sonnet 4.5 pricing
IN  = 3.00 / 1_000_000
OUT = 15.00 / 1_000_000

v1_in, v1_out = 800, 1300        # v1 short prompt + 900w output
v2_in_nr = tok(sys_prompt) + tok(user_no_res)
v2_in_wr = tok(sys_prompt) + tok(user_with_res)
v2_out = 2700                     # 1800w HTML

v1_run   = v1_in   * IN + v1_out * OUT
v2_run_nr = v2_in_nr * IN + v2_out * OUT
v2_run_wr = v2_in_wr * IN + v2_out * OUT

print('=== COST PER RUN ===')
print(f'v1 (900w, short prompt)           : USD {v1_run:.4f}')
print(f'v2 (1800w, no Tavily research)    : USD {v2_run_nr:.4f}')
print(f'v2 (1800w, with Tavily research)  : USD {v2_run_wr:.4f}')
print()

RUNS  = 2   # per day
DAYS  = 30

print('=== MONTHLY COST (2 runs/day x 30 days) ===')
cases = [
    ('v1 baseline (no research, 1 attempt)',        v1_run,   1.0),
    ('v2 no research, 1 attempt',                  v2_run_nr, 1.0),
    ('v2 with research, 1 attempt',                v2_run_wr, 1.0),
    ('v2 with research, avg 1.5 retries',          v2_run_wr, 1.5),
    ('v2 with research, worst case 3 retries',     v2_run_wr, 3.0),
]
for label, cost, retries in cases:
    monthly = cost * retries * RUNS * DAYS
    print(f'  {label:<48s}: USD {monthly:.2f}/mo')

print()
print('=== MULTIPLIER vs v1 ===')
for label, cost, retries in cases[1:]:
    ratio = (cost * retries) / v1_run
    print(f'  {label:<48s}: x{ratio:.1f}')
