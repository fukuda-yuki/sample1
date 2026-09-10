"""Re-read the cited fixed source and visible decision records for all 60 Runs."""
from pathlib import Path
import collections
from analyze import BASE,read,sha,write_json
ROOT=BASE.parents[1]

def main():
    origins={x['run_id']:x for x in read(BASE/'data/provenance.json')}
    runs={x['run_id']:x for x in read(BASE/'data/runs.json')};checked=[]
    for q in read(BASE/'source/qualitative-a.json')['runs']:
        r=runs[q['run_id']];refs=[]
        intent=q.get('recorded_intent',{})
        if intent.get('citation'):refs.append(('decision_record',intent['citation']))
        for branch in q.get('static_implementation',{}).get('branches',[]):refs.append(('fixed_code',branch['citation']))
        evidence=[]
        for kind,c in refs:
            path=Path(c['path']);assert sha(path)==c['sha256'];lines=path.read_text(encoding='utf-8-sig').splitlines()
            lo=c['line_start'];hi=c.get('line_end',lo)
            evidence.append({'kind':kind,'path':str(path),'sha256':c['sha256'],'line_start':lo,'line_end':hi,'read_text':'\n'.join(lines[lo-1:hi])})
        assert any(x['kind']=='fixed_code' for x in evidence),r['label']
        checked.append({'label':r['label'],'run_id':r['run_id'],'condition':r['condition'],'submission_hash':r['submission_hash'],
          'static_threshold_yen':r['static_threshold_yen'],'recorded_threshold_yen':r['recorded_threshold_yen'],
          'explicit_conflict_recorded':r['explicit_conflict_recorded'],'citations':evidence})
    for q in read(BASE/'source/qualitative-b.json')['runs']:
        r=runs[q['run_id']];o=origins[r['run_id']]
        folder=ROOT/'results/acquisition20-20260911/batch/runs'/o['original_label']/'attempt/frozen';evidence=[]
        for c in q['citations']:
            path=folder/c['path'];assert sha(path)==c['sha256'];lines=path.read_text(encoding='utf-8-sig').splitlines();n=c['line']
            assert lines[n-1].strip()==c['text'].strip(),(path,n)
            evidence.append({'kind':'decision_record' if path.suffix.lower()=='.md' else 'fixed_code','path':str(path),'sha256':c['sha256'],
              'line_start':n,'line_end':n,'read_text':lines[n-1]})
        assert any(x['kind']=='fixed_code' for x in evidence),r['label']
        checked.append({'label':r['label'],'run_id':r['run_id'],'condition':r['condition'],'submission_hash':r['submission_hash'],
          'static_threshold_yen':r['static_threshold_yen'],'recorded_threshold_yen':r['recorded_threshold_yen'],
          'explicit_conflict_recorded':r['explicit_conflict_recorded'],'citations':evidence})
    assert len(checked)==60 and len({x['run_id'] for x in checked})==60
    write_json(BASE/'evidence/source-readback.json',{'scope':'Visible submitted records and fixed source only; no hidden reasoning or new runtime verification',
        'runs':sorted(checked,key=lambda x:x['run_id']),'unique_files_read':len({c['path'] for x in checked for c in x['citations']}),'new_app_runs':0,'new_evaluations':0})
    print({'runs_checked':len(checked),'unique_files_read':len({c['path'] for x in checked for c in x['citations']})})

if __name__=='__main__':main()
