import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'bots')
try:
    import senior_config
    print('senior_config OK')
    cat_key, cat_info = senior_config.get_category_for_today()
    print(f'Category: {cat_key} / {cat_info["name"]}')
    kw = senior_config.get_keywords_for_category(cat_key, n=2)
    print(f'Keywords: {kw}')

    import senior_collector
    print('senior_collector OK')
    collected = senior_collector.collect_keywords_for_today()
    print(f'Collected PK: {collected["primary_keyword"]}')

    import senior_generator
    print('senior_generator OK')

    from bots import publisher_bot
    print('publisher_bot OK')

    print('ALL IMPORTS OK')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
