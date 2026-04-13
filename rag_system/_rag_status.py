import json, pathlib
from collections import defaultdict

p = pathlib.Path('D:/James8/FileSystem/rag_system/doc_registry.json')
if not p.exists():
    print('No documents indexed yet.')
else:
    reg = json.loads(p.read_text())
    groups = defaultdict(list)
    for src, info in sorted(reg.items()):
        cat = src.split('/')[0] if '/' in src else '(root)'
        groups[cat].append((src, info.get('chunk_count', '?'), info.get('indexed_at','?')[:10]))
    total = len(reg)
    print(f'Total: {total} documents\n')
    for cat in sorted(groups):
        print(f'[{cat}]')
        for src, chunks, date in groups[cat]:
            print(f'  {src}  ({chunks} chunks, {date})')
