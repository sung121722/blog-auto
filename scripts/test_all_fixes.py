import sys
sys.path.insert(0, 'C:/Users/kang_/Downloads/blog-writer_mcp')
sys.path.insert(0, 'C:/Users/kang_/Downloads/blog-writer_mcp/bots')
sys.stdout.reconfigure(encoding='utf-8')

import json, tempfile
from pathlib import Path

import publish_governor, senior_collector, senior_config, senior_generator
from publish_governor import PublishBlocked, save_published_title, save_draft
from senior_collector import get_used_hook_angles, mark_hook_used
from senior_config import get_hook_for_category
from senior_generator import _parse_json, _sanitize_year

results = []

def check(name, fn):
    try:
        fn()
        results.append((name, 'OK'))
        print(f'[OK] {name}')
    except Exception as e:
        results.append((name, f'FAIL: {e}'))
        print(f'[FAIL] {name}: {e}')

# 1. Hook deduplication
def test_hook_dedup():
    used = {'Medicare enrollment window misconception'}
    hook = get_hook_for_category('A', used_angles=used)
    assert hook['hook_angle'] not in used or not hook['hook_angle'], \
        f"Got excluded angle: {hook['hook_angle']}"
check('Hook deduplication', test_hook_dedup)

# 2. Governor logging
def test_gov_log():
    publish_governor._GOV_LOG = Path(tempfile.mktemp(suffix='.jsonl'))
    article = {
        'title': 'RMD Rules After 73 in 2026',
        'meta': 'Learn RMD.',
        '_html_content': '<p>' + ' '.join(['word']*1500) + '</p>',
        'tags': ['retirement'],
        '_fixed_labels': ['Retirement'],
    }
    publish_governor.run(article)
    assert publish_governor._GOV_LOG.exists()
    record = json.loads(publish_governor._GOV_LOG.read_text())
    assert record['title'] == 'RMD Rules After 73 in 2026'
    assert record['word_count'] >= 1400
check('Governor log file', test_gov_log)

# 3. Draft save on block
def test_draft_save():
    article = {'title': 'Test Draft', 'meta': '', '_html_content': '<p>short</p>', 'tags': []}
    path = save_draft(article, '[HARD] test block reason')
    assert path.exists()
    data = json.loads(path.read_text())
    assert data['block_reason'] == '[HARD] test block reason'
check('Draft save on block', test_draft_save)

# 4. Duplicate title detection
def test_dup_title():
    publish_governor._TITLE_LOG = Path(tempfile.mktemp(suffix='.json'))
    save_published_title('Required Minimum Distribution Rules After 73 in 2026')
    msg = publish_governor._check_duplicate_title(
        'Required Minimum Distribution After 73 in 2026'
    )
    assert msg is not None, 'Expected duplicate detection but got None'
    # Different title should not trigger
    msg2 = publish_governor._check_duplicate_title(
        'How to Choose Medicare Part D Drug Coverage'
    )
    assert msg2 is None, f'False positive: {msg2}'
check('Duplicate title detection', test_dup_title)

# 5. _sanitize_year preserves historical dates
def test_sanitize_year():
    data = {
        'title': 'RMD Guide 2024',
        'meta_description': 'Rules for 2024',
        'html_content': (
            '<h2>RMD Rules in 2024</h2>'
            '<p>SECURE 2.0 was signed in 2022. '
            'Medicare started in 2006. '
            'The law changed as of 2023.</p>'
        )
    }
    result = _sanitize_year(data)
    assert '2026' in result['title']
    assert '2026' in result['meta_description']
    assert 'in 2026' in result['html_content']       # h2 updated
    assert 'signed in 2022' in result['html_content'] # historical preserved
    assert 'as of 2023' in result['html_content']     # SECURE 2.0 date preserved
check('_sanitize_year preserves history', test_sanitize_year)

# 6. JSON truncation recovery
def test_json_recovery():
    # Truncated after html_content value
    truncated = '{"title": "Test Post", "meta_description": "Test meta", "html_content": "<h2>Section</h2><p>Content here</p><p>More content'
    result = _parse_json(truncated)
    assert result.get('title') == 'Test Post'
    assert 'html_content' in result
check('JSON truncation recovery', test_json_recovery)

# Summary
print()
passed = sum(1 for _, s in results if s == 'OK')
print(f'{passed}/{len(results)} tests passed')
if passed < len(results):
    for name, status in results:
        if status != 'OK':
            print(f'  FAILED: {name} -> {status}')
