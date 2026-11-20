from pathlib import Path
import gzip,hashlib,json,os
ROOT=Path(__file__).resolve().parent
PREV=ROOT.parents[1]/'memory_session3'/'procedure'
SUB={'claude':'20260217_mini-v2.0.0_claude-4-6-opus','codex':'20260219_mini-v2.0.0_gpt-5-2-codex','gemini':'20260901_mini-v2.4.2_gemini-3-5-flash'}
MODELS=list(SUB);REG='40f164d5b8f1d249bf95a6df8b74b577fd8e519d';GEM='2f6637a2557da1f7b5f2b583ab7090a077bbeed2'
S3='https://swe-bench-submissions.s3.amazonaws.com/'
def sha(b):return hashlib.sha256(b if isinstance(b,bytes) else b.encode()).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(',',':'))
def read(n):
    p=ROOT/n;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def write(n,v):
    p=ROOT/n;p.parent.mkdir(parents=True,exist_ok=True);s=canon(v).encode();t=p.with_suffix(p.suffix+'.tmp');t.write_bytes(gzip.compress(s,compresslevel=5,mtime=0) if p.suffix=='.gz' else s);os.replace(t,p)
def seal(files):return {f:sha((ROOT/f).read_bytes()) for f in sorted(files)}
def check(n):
    files=read(n);assert files==seal(files),n
def pick(i):return 'claude' if int(sha('tie-s4|'+i),16)%2==0 else 'codex'
