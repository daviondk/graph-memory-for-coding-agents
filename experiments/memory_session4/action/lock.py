import hashlib,json,datetime
from pathlib import Path
P=Path(__file__).resolve().parent
names=['PROTOCOL.md','SCHEMA_PRELOCK.md','LOG_READ_PRELOCK.md','FEEDBACK_PRELOCK.md','model.py','project.py','run.py','source.json','job_sources.json','EXTERNAL_PRELOCK.md','external_collect.py','bson_stream.py']
names += [kind+'_'+piece+'.jsonl.gz' for kind in ['builds','jobs'] for piece in ['inputs','labels']]
dest=P/'input_lock.json'
d={n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in names}
if dest.exists():assert d==json.loads(dest.read_text())['sha256']
else:dest.write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':d},indent=1))
