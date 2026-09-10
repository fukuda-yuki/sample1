"""Execute named read-only SQL queries for inspectable claims and cross-checks."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sqlite3

BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build(database,output):
    connection=sqlite3.connect(database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    connection.row_factory=sqlite3.Row
    queries=(BASE/'queries.sql').read_text(encoding='utf-8-sig')
    sections=re.split(r'^-- claim: (\w+)\s*$',queries,flags=re.M)
    result={}
    for name,sql in zip(sections[1::2],sections[2::2]):
        rows=[dict(r) for r in connection.execute(sql)]
        result[name]={'sql':sql.strip(),'rows':rows}
    connection.close()
    output.parent.mkdir(parents=True,exist_ok=True)
    value={'database_sha256':sha(database),'queries_sha256':sha(BASE/'queries.sql'),
        'database_access':'SQLite read-only immutable URI','queries':result}
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'queries':len(result),'result_rows':sum(len(x['rows']) for x in result.values())}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',type=Path,default=BASE/'data/analysis.sqlite');p.add_argument('--output',type=Path,default=BASE/'data/sql-evidence.json');a=p.parse_args();build(a.database,a.output)
