"""Build public query strata without reading predictions, evidence spans or outcomes."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import requests

ROOT = Path(__file__).resolve().parent
REV = 'a98e2c30285a6d557a8b429e59a1a6eb27738537'
URL = f'https://raw.githubusercontent.com/xiaoqi-7/GraphMemory/{REV}/scripts/feeds_lexical_stratify.py'
QUERIES = Path('D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl')
SPLIT = ROOT.parents[1]/'graph_memory_round22/native_multiseed/official580/split.json.gz'
def digest(data):
    return hashlib.sha256(data).hexdigest()
def main():
    response = requests.get(URL, timeout=20)
    response.raise_for_status()
    matches = [n for n in ast.parse(response.text).body if isinstance(n, ast.Assign) and any(getattr(lhs,'id',None)=='PATTERN' for lhs in n.targets)]
    assert len(matches)==1
    call=matches[0].value
    assert call.func.attr=='compile' and call.args[1].attr=='IGNORECASE'
    pattern = ast.literal_eval(call.args[0])
    compiled = re.compile(pattern, re.IGNORECASE)
    wanted={r['q'] for r in json.loads(gzip.decompress(SPLIT.read_bytes()))['test']}
    flags={}
    with QUERIES.open(encoding='utf8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['id'] in wanted:
                assert row['id'] not in flags
                flags[row['id']]=bool(compiled.search(row['query']))
    assert len(flags)==len(wanted)==2000
    data=gzip.compress(json.dumps(flags,sort_keys=True,separators=(',',':')).encode(),mtime=0)
    (ROOT/'strata.json.gz').write_bytes(data)
    record={'source':URL,'pattern':pattern,'source_sha256':digest(response.content),'strata_sha256':digest(data),'protocol_sha256':digest((ROOT/'PROTOCOL_RU.md').read_bytes()),'query_source_sha256':digest(QUERIES.read_bytes()),'split_sha256':digest(SPLIT.read_bytes())}
    (ROOT/'label-lock.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print(len(flags),'questions labeled',sum(flags.values()),'with identifiers')
if __name__=='__main__':
    main()
