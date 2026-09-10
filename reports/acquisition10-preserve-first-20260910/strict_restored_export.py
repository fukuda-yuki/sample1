"""Re-export a restored corpus while denying every original evaluation location.

This checks Python file-open and SQLite access, not an OS-wide sandbox.
The copied management code performs the export; this file is only its guard.
"""
import argparse,hashlib,json,os,sqlite3,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('restored',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--forbid',type=Path,action='append',default=[])
args=parser.parse_args();restored=args.restored.resolve();out=args.output.resolve()
check_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
payload=restored/'payload';mapping=restored/'restoration-map.json'
assert mapping.is_file() and (payload/'evaluation-locations.json').is_file()
locations=json.loads((payload/'evaluation-locations.json').read_text())
forbidden={str(p.resolve()) for p in args.forbid}
forbidden.update(str(Path(v['original_directory']).resolve()) for v in locations.values())
index=json.loads((payload/'batch/run-index.json').read_text())
assert sum(bool(r['run_id']) for r in index['runs'])==20,'This check is bound to the completed 20-Run corpus'
assert len(locations)>=20,'Keep every selected evaluation and its preserved history'
assert forbidden and not any(out==Path(p) or out.is_relative_to(Path(p)) or payload==Path(p) or payload.is_relative_to(Path(p)) for p in forbidden)
out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(payload/'management/scripts'))
from copilot_batch import export

def normalized(value):
 value=os.fsdecode(value)
 if value.startswith('file:'):
  parsed=urlsplit(value)
  value=unquote(parsed.path)
  if parsed.netloc not in ('','localhost'):value='//'+parsed.netloc+value
 return str(Path(value).resolve())

def guard(event,values):
 if event not in ('open','sqlite3.connect') or not values or not isinstance(values[0],(str,bytes,os.PathLike)):return
 path=normalized(values[0])
 if any(path==p or path.startswith(p+os.sep) for p in forbidden):
  raise PermissionError('Original-data read rejected by restored-only verification')

directory_probes={p for p in forbidden if Path(p).is_dir()}
sys.addaudithook(guard)
probes=0
for original in sorted(forbidden):
 target=Path(original)/'read-denial-probe'
 calls=[lambda p=target:open(p,'rb'),lambda p=target:sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)]
 # A direct-path SQLite probe targets an existing directory: even a broken
 # guard cannot create a new database or modify an original data file here.
 if original in directory_probes:calls.append(lambda p=original:sqlite3.connect(p))
 for call in calls:
  try:call()
  except PermissionError:probes+=1
  else:raise AssertionError('An original-path read was not denied')
try:export(payload/'batch',payload/'validity.json',output=out/'without-map')
except (PermissionError,FileNotFoundError):pass
else:raise AssertionError('An unmapped original reference was accepted')
counts=export(payload/'batch',payload/'validity.json',output=out/'export',restoration_map=mapping)
assert counts['started']==20 and counts['evaluation_completed']==20
result=dict(kind='strict-restored-only-export',model_called=False,source_reads_denied=True,
 original_evaluation_directories_denied=len(locations),denial_probe_count=probes,
 guarded_apis=['Python file open','SQLite path','SQLite file URI'],forbidden_paths=sorted(forbidden),
 unmapped_export_rejected=True,counts=counts,
 check_code_sha256=check_code_sha256,
 scope='Known original paths and prior exports are denied in this process; not an OS-wide air gap.')
(out/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(started=counts['started'],evaluations=counts['evaluation_completed'],denied_evaluation_directories=len(locations),denial_probes=probes)))
