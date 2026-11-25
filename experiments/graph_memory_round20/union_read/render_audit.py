"""Rebuild all strict public records as literal text through Hugging Face AutoTokenizer."""
from collections import defaultdict
from pathlib import Path
import gzip
import hashlib
import json
import os
import sys
import time

os.environ["TOKENIZERS_PARALLELISM"]="false"
os.environ["HF_HUB_OFFLINE"]="1"
from transformers import AutoTokenizer

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get("X20_DATA","D:/CodexResearch"))
BASE=DATA/"x20-isetrace-runtime/e5-base-v2"
CACHE=DATA/"x20-isetrace-e5-gpu/cache/projection"


def load(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)


def sha(data):return hashlib.sha256(data).hexdigest()


def run(model):
    start=time.perf_counter()
    seal=load(ROOT/f"{model}-strict-seal.json");tok=AutoTokenizer.from_pretrained(str(BASE),use_fast=True,local_files_only=True)
    assert tok.is_fast
    tok.model_max_length=10**8
    descriptors=[]
    seen_ids=set()
    stats=defaultdict(lambda:dict(n=0,tok=0,chars=0,bytes=0,parts=0,maximum=0))
    for i,m in enumerate(seal["shards"]):
        path=ROOT/m["file"];assert sha(path.read_bytes())==m["sha"]
        group=defaultdict(list)
        for r in load(path):group[r["t"]].append(r)
        for t,rows in group.items():
            project=load(CACHE/f"{i}-{t}.json.gz");src=project["fields"]
            values=[];metas=[]
            for r in rows:
                assert r["q"] not in seen_ids;seen_ids.add(r["q"])
                for name,parts in sorted(r["a"].items()):
                    fields=[]
                    for e,p,a,b,token_cost in parts:
                        assert 0<=a<b<=len(src[e]) and (p=="/content" or p.startswith("/"))
                        fields.append(src[e][a:b])
                    joined="\n".join(fields);values.append(joined)
                    metas.append((name,r["q"],sum(w[4] for w in parts),len(parts)))
            enc=tok(values,add_special_tokens=False,padding=False,truncation=False,return_attention_mask=False,
                    return_token_type_ids=False,return_length=True,verbose=False)
            for (name,q,expected,nparts),literal,n,ids in zip(metas,values,enc["length"],enc["input_ids"],strict=True):
                assert len(ids)==n==expected<=2048
                byte=literal.encode("utf8")
                descriptors.append((q,name,sha(byte),n,len(byte)))
                v=stats[name];v["n"]+=1;v["tok"]+=n;v["chars"]+=len(literal);v["bytes"]+=len(byte)
                v["parts"]+=nparts;v["maximum"]=max(n,v["maximum"])
    fingerprint=sha(json.dumps(sorted(descriptors),separators=(",",":")).encode())
    assert len(seen_ids)==2000 and len(descriptors)==12000
    result=dict(render_sha256=fingerprint,strict_forecasts_sha256=sha((ROOT/f"{model}-strict-seal.json").read_bytes()),
        source_tokenizer_sha256=sha((BASE/"tokenizer.json").read_bytes()),wrapper=type(tok).__name__,
        seconds=time.perf_counter()-start,query_count=len(seen_ids),literal_documents=len(descriptors),by_arm=stats)
    (ROOT/f"{model}-render-audit.json").write_bytes((json.dumps(result,sort_keys=True,indent=2)+"\n").encode())
    print(model,len(descriptors),"literal documents verified",fingerprint)


if __name__=="__main__":run(sys.argv[1])
