"""Generate a past-only input artifact from fields whose generation is documented as pre-boundary."""
import gzip,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
with (ROOT.parent/'source/chains.jsonl').open(encoding='utf8') as f,gzip.open(ROOT/'prefixes.jsonl.gz','wt',encoding='utf8') as o:
    for i,line in enumerate(f):
        for j,b in enumerate(json.loads(line)['per_k']):
            o.write(json.dumps({'i':i,'j':j,'summary':b['S_k'],'writes':b['done_files']},ensure_ascii=False)+'\n')

