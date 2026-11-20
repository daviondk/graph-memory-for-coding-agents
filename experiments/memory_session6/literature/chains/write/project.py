"""Save only anonymized membership of production Python files inferred from diff headers."""
import gzip
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath

import pyarrow.parquet as pq
import requests

ROOT=Path(__file__).resolve().parent
REV='dcaa484eca5b38caca71420712b1b194c1235d6e'
URL=f'https://huggingface.co/datasets/C-lister/ChainSWE/resolve/{REV}/data/unique.parquet'
EXPECTED='f7de0d66b64a9d5c28921fba2bbd51b5131dae8d5c789e03e61c09e67fc355fe'
DENY=re.compile(r'\b(?:security|injection|exploit|vulnerability|vulnerabilities|CVE|bypass|malware|intrusion|virus|pathogen|toxin|weapon|privilege escalation|authentication|authorization|cryptographic)\b',re.I)
def h(s):return hashlib.sha256(s.encode()).hexdigest()[:24]
def main():
    resp=requests.get(URL,timeout=50);resp.raise_for_status()
    assert hashlib.sha256(resp.content).hexdigest()==EXPECTED
    table=pq.ParquetFile(io.BytesIO(resp.content))
    output=[]
    columns=['continuous_id','repo','bug_fixes.list.element.swebench_instance_id','bug_fixes.list.element.problem_statement','bug_fixes.list.element.patch']
    for row in table.read(columns=columns).to_pylist():
        repo=row['repo'];steps=[]
        for item in row['bug_fixes']:
            files={}
            eligible=not DENY.search(item['problem_statement'] or '')
            if eligible:
                for path in re.findall(r'^diff --git a/[^\s]+ b/([^\s]+)\s*$',item['patch'] or '',flags=re.M):
                    parts=PurePosixPath(path).parts
                    name=parts[-1].lower()
                    if (not name.endswith('.py') or name.startswith('test_') or name.endswith('_test.py') or name=='conftest.py' or
                        any(p.lower() in {'tests','test','testing','vendor','vendors','vendored','third_party','generated'} for p in parts) or DENY.search(path.replace('_',' '))):
                        continue
                    files[h(repo+'#'+path)]=h(repo+'#dir#'+'/'.join(parts[:-1]))
            steps.append({'issue':h(repo+'#issue#'+item['swebench_instance_id']),'allowed':bool(eligible),'files':files})
        output.append({'sequence':h(row['continuous_id']),'repo':repo,'steps':steps})
    data=json.dumps(output,separators=(',',':'),sort_keys=True).encode()
    dst=ROOT/'projection.json.gz';packed=gzip.compress(data,mtime=0)
    if dst.exists():assert dst.read_bytes()==packed
    else:dst.write_bytes(packed)
    print('projected sequences',len(output))
if __name__=='__main__':main()
