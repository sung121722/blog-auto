import sys, json, re
from pathlib import Path
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding='utf-8')

files = sorted(Path('data').glob('quality_compare_*.json'))
if not files:
    print('No compare files found')
    exit()

data = json.loads(files[-1].read_text(encoding='utf-8'))
print(f'File: {files[-1].name}')
print(f'Category: {data["category"]} | Keyword: {data["keyword"]}')
print()

for r in data['results']:
    print(f'{"="*60}')
    print(f'MODEL: {r["model"]}')
    if not r.get('success'):
        print(f'FAILED: {r.get("error")}')
        continue

    print(f'Title:        {r["title"]}')
    print(f'Word Count:   {r["word_count"]}')
    print(f'Banned Hard:  {r["banned_hard"]} ({r["banned_hard_count"]} hits)')
    print(f'Persona /7:   {r["persona_total"]} {r["persona_score"]}')
    print(f'Specific $$:  {bool(r["has_specific_numbers"])}')

    # Full HTML preview
    html_preview = r.get('html_preview', '')
    text = BeautifulSoup(html_preview, 'html.parser').get_text()
    print()
    print('--- CONTENT PREVIEW (first 600 chars) ---')
    print(text[:600])

    # Dollar amounts
    dollar_amts = re.findall(r'\$[\d,]+', text)
    print()
    print(f'Dollar amounts found: {dollar_amts[:15] if dollar_amts else "NONE"}')
    print()

# Read actual full saved JSON for full HTML
print('=== FULL JSON file path:', files[-1])
