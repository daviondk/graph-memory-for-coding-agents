"""Only the currently completed event may determine a block's feature row."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import math
import re
import sys
import numpy as np
ROOT=Path(__file__).resolve().parent;ONLINE=ROOT.parent/"online_write";TRAINED=ROOT.parent/"trained_rank"
sys.path.insert(0,str(ONLINE))
import predict as stream
import byte_memory as binary

POSITION=["output","log_depth","log_reverse_depth","relative_depth","first","last","log_field_blocks","log_field_tokens",
          "log_block_tokens","output_x_depth","output_x_reverse","output_x_relative"]
SHAPE=["alpha_fraction","digit_fraction","whitespace_fraction","newline_fraction","punctuation_fraction","slash_fraction","colon_equals_fraction",
       "has_url","has_path","has_hex_id","has_error","has_assignment"]
URL=re.compile(r"https?://",re.I);PATH=re.compile(r"(?:[A-Za-z]:[\\/]|/(?:[\w.-]+/)|\\[\w.-]+\\)")
HEX=re.compile(r"\b(?:[0-9a-f]{12,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b",re.I)
ERR=re.compile(r"\b(?:error|exception|failed|failure|invalid|not found|warning)\b",re.I)
ASSIGN=re.compile(r"(?:[\w.-]+\s*=|[\"']\s*:)")
def save(path,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()+b"\n"
    if path.suffix==".gz":b=gzip.compress(b,mtime=0)
    tmp=path.with_suffix(".tmp");tmp.write_bytes(b);tmp.replace(path)
def load(path):
    b=path.read_bytes();return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def sha(p):return stream.digest(p)
def tool_lookup(pool):
    out={}
    for c in pool:
        for sp in c["source_spans"]:
            eid=sp["event_id"];name=c["metadata"].get("tool_name") or "<unknown>"
            assert eid not in out or out[eid]==name
            out[eid]=name
    return out
def rows(addresses,blocks,fields,tool):
    # Whole-event length/depth is known after it arrives, independent of other events.
    grouped=Counter();total=Counter();seen=Counter();features=[];names=[]
    for e,a,b,c,nbyte in blocks:grouped[e]+=1;total[e]+=c
    for e,a,b,c,nbyte in blocks:
        eid,ptr=addresses[e];size=grouped[e];j=seen[e];seen[e]+=1
        is_out=float(ptr=="/content");ld=math.log1p(j);lr=math.log1p(size-1-j);rel=j/max(size-1,1)
        start=[is_out,ld,lr,rel,float(j==0),float(j==size-1),math.log1p(size),math.log1p(total[e]),math.log1p(c),is_out*ld,is_out*lr,is_out*rel]
        text=fields[eid][a:b];n=max(1,len(text))
        shape=[sum(map(str.isalpha,text))/n,sum(map(str.isdigit,text))/n,sum(map(str.isspace,text))/n,text.count("\n")/n,
            sum(z in '{}[],:;=()<>|\"\'\\/' for z in text)/n,(text.count("/")+text.count("\\"))/n,(text.count("=")+text.count(":"))/n,
            bool(URL.search(text)),bool(PATH.search(text)),bool(HEX.search(text)),bool(ERR.search(text)),bool(ASSIGN.search(text))]
        features.append(start+shape);names.append(tool[eid])
    return np.asarray(features,dtype=np.float64),names

def design(x,tools,vocab,full):
    if not full:return x[:,:len(POSITION)]
    onehot=np.zeros((len(x),len(vocab)))
    index={k:j for j,k in enumerate(vocab)}
    for i,k in enumerate(tools):
        if k in index:onehot[i,index[k]]=1.0
    return np.column_stack((x,onehot))
