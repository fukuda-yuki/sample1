"""Describe measurement coverage without changing the fixed score denominator."""
from collections import Counter


def summarize(cases, *, attempted=False, validity='pending'):
    features = {}
    ids = {}
    causes = Counter()
    responsibilities=Counter()
    cause_references=[]
    for row in cases:
        feature = 'F-' + row['evaluation_id'].split('-')[1]
        f = features.setdefault(feature, {'ids': set(), 'cases': 0, 'business_assertion_reached': 0,
            'prerequisite_blocked': 0, 'evaluation_unresolved': 0, 'unknown': 0, 'raw_pass_cases': 0})
        f['ids'].add(row['evaluation_id']); f['cases'] += 1
        ids.setdefault(row['evaluation_id'],[]).append(row)
        f['raw_pass_cases'] += row['status'] == 'pass'
        evidence = row.get('evidence')
        decision=evidence.get('adjudication') if isinstance(evidence,dict) else None
        responsibilities[decision['responsibility'] if decision else 'unconfirmed' if row['status']!='pass' else 'none']+=1
        if decision:
            cause_references.append({k:decision.get(k) for k in ('evaluation_id','case_id','responsibility','root_event','adjudication_sha256')})
        measurement = evidence.get('measurement') if isinstance(evidence, dict) else None
        if not measurement:
            f['unknown'] += 1
            continue
        cause = measurement.get('cause', 'unconfirmed')
        causes[cause] += 1
        if measurement.get('business_assertion_reached') is True:
            f['business_assertion_reached'] += 1
        if row['status'] == 'blocked' and measurement.get('prerequisite'):
            f['prerequisite_blocked'] += 1
        if cause in ('target_discovery', 'evaluator', 'evaluation_environment', 'unconfirmed'):
            f['evaluation_unresolved'] += 1
    for f in features.values():
        target=f.pop('ids');f['target_ids'] = len(target)
        f['raw_pass_ids']=sum(all(r['status']=='pass' for r in ids[i]) and len(ids[i])==(2 if i=='T-006-05' else 1) for i in target)
        f['raw_quality_percent']=100*f['raw_pass_ids']/len(target)
        f['effective_quality_percent']=f['raw_quality_percent'] if validity=='valid' else None
    return {'schema_version': 1, 'coverage_unit': 'required_case', 'fixed_ids': 57,
        'required_cases': 58, 'evaluation_attempted': attempted,
        'evaluation_completed': attempted and len(cases) == 58,
        'measurement_state': validity if attempted else 'not_attempted',
        'features': features, 'causes': dict(causes),'responsibilities':dict(responsibilities),'cause_references':cause_references}
