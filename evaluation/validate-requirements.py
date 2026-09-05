"""Validate the fixed private evaluation denominator and audited source ledger."""
import collections
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'test_items.md').read_text(encoding='utf-8')
ledger = json.loads((root / 'evaluation/requirements-ledger.json').read_text(encoding='utf-8'))
headings = re.findall(r'^### (T-\d{3}-\d{2}) ([^\n]+)', source, re.M)
ids = [item[0] for item in headings]
assert len(ids) == len(set(ids)) == ledger['fixed_denominator'] == 57
expected_counts = [4,4,2,3,2,6,3,4,2,3,2,2,2,2,1,3,2,3,3,4]
expected_ids = [f'T-{f:03d}-{n:02d}' for f, count in enumerate(expected_counts, 1) for n in range(1,count+1)]
assert ids == expected_ids, '欠番・順序・機能別件数の不一致'
assert [item['evaluation_id'] for item in ledger['items']] == ids
counts = collections.Counter('正常系' if '🟢' in title else '境界値' if '🟡' in title else '異常系' for _, title in headings)
assert counts == {'正常系':32, '境界値':3, '異常系':22} == ledger['categories']
for label, count in counts.items():
    assert f'| {label}テスト | {count}件 |' in source
assert '| **合計** | **57件** |' in source
for item in ledger['items']:
    for key in ['public_basis','inputs_and_preconditions','required_external_behavior','allowed_realizations','evaluator_operations','scoring_unit','decision','audit_note','ap001_relation']:
        assert item[key], (item['evaluation_id'], key)
    assert item['scoring_unit']['id_count'] == 1
    assert item['scoring_unit']['required_subcases'] == (2 if item['evaluation_id']=='T-006-05' else 1)
    for basis in item['public_basis']:
        path=root / basis['file']
        assert path.is_file(), basis
        if basis['feature'].startswith('F-'):
            assert f"## {basis['feature']}:" in path.read_text(encoding='utf-8'), basis
normal=(root/'normal/spec.md').read_text(encoding='utf-8')
anti=(root/'anti/spec.md').read_text(encoding='utf-8')
assert normal.count('**999,999円以下**')==1 and normal.count('**1,000,000円以上**')==1
assert anti == normal.replace('**999,999円以下**','**499,999円以下**').replace('**1,000,000円以上**','**500,000円以上**'), 'AP-001以外の仕様差分'
print('PASS: 57 IDs; normal=32 boundary=3 negative=22; sequential per-feature IDs; ledger/summary; AP-001 preserved')
