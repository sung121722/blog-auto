import sys
sys.path.insert(0, 'C:/Users/kang_/Downloads/blog-writer_mcp')
sys.stdout.reconfigure(encoding='utf-8')
import publish_governor
from publish_governor import PublishBlocked

BASE = '<p>' + ' '.join(['word']*1000) + ' '

tests = [
    # (description, snippet, should_block)
    ('RMD begins at 72 BLOCK',      'If your RMD begins at age 72 then you must take it.',          True),
    ('RMD historical 72->73 PASS',  'The age shifted from 72 to 73 under SECURE 2.0.',              False),
    ('SS FRA is 65 BLOCK',          'your full retirement age is 65 when you can claim',            True),
    ('FRA used to be 65 PASS',      'full retirement age used to be 65 for earlier cohorts',        False),
    ('donut hole enter BLOCK',      'you will fall into the donut hole at that point',              True),
    ('donut hole before 2025 PASS', 'before 2025 the donut hole cost seniors money',               False),
    ('IRA limit $6000 BLOCK',       'IRA contribution limit is $6,000 per year',                   True),
    ('IRA was $6000 2022 PASS',     'the limit was 6,000 in 2022 before the increase',             False),
    ('BANNED_HARD journey BLOCK',   'this journey is seamlessly done',                             True),
    ('CJK BLOCK',                   '테스트 Korean text here',                                      True),
    ('short content BLOCK',         ' '.join(['word']*50),                                         True),  # only 50 words total
]

pass_count = 0
for name, snippet, should_block in tests:
    # For the short content test, use snippet as the entire html
    if 'short content' in name:
        html = '<p>' + snippet + '</p>'
    else:
        html = BASE + snippet + '</p>'
    article = {'title': 'Test Article', 'meta': 'test meta', '_html_content': html, 'tags': []}
    try:
        publish_governor.run(article)
        blocked = False
    except PublishBlocked:
        blocked = True
    except Exception as e:
        blocked = False
        print(f'[ERROR] {name}: {e}')
        continue
    status = 'OK' if blocked == should_block else 'FAIL'
    if status == 'OK':
        pass_count += 1
    print(f'[{status}] {name}  ->  blocked={blocked} (expected={should_block})')

print(f'\n{pass_count}/{len(tests)} tests passed')
