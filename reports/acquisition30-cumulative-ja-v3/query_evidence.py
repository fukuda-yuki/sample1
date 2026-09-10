"""Run every report SQL query against the normalized 60-Run database."""
from pathlib import Path
import argparse,json,re,sqlite3
BASE=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data',type=Path,default=BASE/'data');a=ap.parse_args()
    db=sqlite3.connect((a.data/'analysis.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    parts=re.split(r'^-- (Q\d+_\w+)\s*$',(BASE/'queries.sql').read_text(encoding='utf-8'),flags=re.M)
    evidence={parts[i]:{'sql':parts[i+1].strip(),'rows':[dict(r) for r in db.execute(parts[i+1])]} for i in range(1,len(parts),2)}
    (a.data/'sql-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'queries':len(evidence),'rows':sum(len(x['rows']) for x in evidence.values())}))
if __name__=='__main__':main()
