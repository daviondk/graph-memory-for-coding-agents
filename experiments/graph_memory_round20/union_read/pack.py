"""Freeze and apply the same lossless source-quote packing rules to either ranking."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ["TOKENIZERS_PARALLELISM"]="false"
os.environ["OPENBLAS_NUM_THREADS"]="1"
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
RUNTIME=Path(os.environ.get("X20_DATA","D:/CodexResearch"))
CACHE=RUNTIME/"x20-isetrace-e5-gpu/cache/projection"
TOKENIZER=RUNTIME/"x20-isetrace-runtime/inputs/tokenizer.json"
R18=WORK/"graph_memory_round18"
R19=WORK/"graph_memory_round19"
OFF=R18/"isetrace_official"
CAP=2048
sys.path.insert(0,str(RUNTIME/"x20-isetrace-runtime/upstream"))
from graph_memory.text.tokens import content_tokens
from tokenizers import Tokenizer


def load(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)


def put(path,data):
    raw=(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0,compresslevel=4) if path.suffix==".gz" else raw)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def rankpath(method,i):
    if method=="dense":
        return R19/"trained_rank"/f"forecasts-main-{i}.json.gz"
    assert method=="rgcn"
    return ROOT.parent/"residual_graph"/f"forecasts-rgcn-{i}.json.gz"


def common_plan():
    source_registry=R18/"isetrace_e5/inventory.json"
    digest=hashlib.sha256()
    pro=list(sorted(CACHE.glob("*.json.gz")));assert len(pro)==1207
    for p in pro:
        digest.update(p.name.encode()+b"\0"+bytes.fromhex(sha(p)))
    assert digest.hexdigest()==load(source_registry)["projection_digest"]
    info=dict(protocol=sha(ROOT/"PROTOCOL_RU.md"),code=sha(ROOT/"pack.py"),inventory=sha(source_registry),
         native_tokenizer=sha(TOKENIZER),projection_digest=digest.hexdigest(),cohort=sha(OFF/"cohort.json"),
         ranks=["dense","rgcn"])
    put(ROOT/"design-lock.json",info)


def model_plan(method):
    common=load(ROOT/"design-lock.json")
    assert common["code"]==sha(ROOT/"pack.py") and common["protocol"]==sha(ROOT/"PROTOCOL_RU.md")
    base=rankpath(method,0).parent
    candidates=[base/"forecast-seal.json"] if method=="dense" else [base/"forecast-seal.json",base/"MANIFEST_SHA256.json",base/"rgcn-forecast-seal.json"]
    plans={f.name:sha(f) for f in candidates if f.exists()}
    expected={rankpath(method,i).name:sha(rankpath(method,i)) for i in range(8)}
    def pairs(node):
        if isinstance(node,dict):
            for k,v in node.items():
                if isinstance(v,str):yield k,v
                else:yield from pairs(v)
        elif isinstance(node,list):
            for val in node:yield from pairs(val)
    trusted={k:v for n in plans for k,v in pairs(load(base/n))}
    assert all(trusted.get(k)==v for k,v in expected.items()),"missing checked upstream forecast seal"
    put(ROOT/(method+"-plan.json"),dict(ranks=expected,upstream=plans,design=sha(ROOT/"design-lock.json")))


def merge(intervals):
    out=[]
    for a,b in sorted(intervals):
        if out and a<=out[-1][1]:
            out[-1]=(out[-1][0],max(b,out[-1][1]))
        else:out.append((a,b))
    return out


def gaps(a,b,seen):
    cursor=a
    for left,right in seen:
        if right<=cursor:continue
        if left>=b:break
        if left>cursor:yield cursor,min(left,b)
        cursor=max(cursor,right)
    if cursor<b:yield cursor,b


def includes(before,after):
    return all(not list(gaps(a,b,after.get(k,[]))) for k,ivs in before.items() for a,b in ivs)


class Episode:
    def __init__(self,project,tok):
        self.fields=project["fields"]
        self.q=dict(project["q"])
        self.spans={}
        self.tok=tok
        self.answers={}
        self.offset_map={}
        for item in project["pool"]:
            n=item["item_id"];ss=item["source_spans"];assert len(ss)==1 and n not in self.spans
            s=ss[0];e,p=s["event_id"],s["json_pointer"];a,b=s["char_start"],s["char_end"]
            assert 0<=a<b<=len(self.fields[e])
            self.spans[n]=((e,p),a,b)

    def cost(self,key,a,b):
        address=(key,a,b)
        if address not in self.answers:
            ss=self.fields[key[0]][a:b]
            self.answers[address]=len(self.tok.encode(ss,add_special_tokens=False).ids)
        return self.answers[address]

    def offsets(self,k,a,b):
        loc=(k,a,b)
        if loc not in self.offset_map:
            enc=self.tok.encode(self.fields[k[0]][a:b],add_special_tokens=False)
            self.offset_map[loc]=[(i+a,j+a) for i,j in enc.offsets if i<j]
        return self.offset_map[loc]

    def windows(self,k,a,b,width):
        off=self.offsets(k,a,b)
        if not off:return
        last=max(0,len(off)-width)
        for start in sorted({*range(0,last+1,max(1,width//2)),last}):
            stop=min(len(off),start+width)
            yield (a if start==0 else off[start][0], b if stop==len(off) else off[stop-1][1])

    def pack(self,row):
        rr=row["rr"];rank=[n["node_id"] for n in rr]
        costs={n["node_id"]:n["token_count"] for n in rr}
        assert set(rank)==self.spans.keys() and len(rank)==len(costs) and all(v>0 for v in costs.values())
        origin=[];used=0
        for node in rr:
            nid=node["node_id"];c=node["token_count"]
            s=node["source_spans"][0];assert len(node["source_spans"])==1
            assert self.spans[nid]==((s["event_id"],s["json_pointer"]),s["char_start"],s["char_end"])
            if used+c<=CAP:origin.append(nid);used+=c
        assert origin==row["arms"]["skip"]
        base=[];raw=defaultdict(list)
        for i in origin:
            k,a,b=self.spans[i];raw[k].append((a,b));base.append([*k,a,b,costs[i]])
        canon={k:merge(v) for k,v in raw.items()}
        state=dict(canon)
        by_field={k:sum(self.cost(k,a,b) for a,b in v) for k,v in state.items()}
        spent=sum(by_field.values())
        def flatten(st):
            return [[*k,a,b,self.cost(k,a,b)] for k,ivs in st.items() for a,b in ivs]
        def surface(records):
            actual="\n".join(self.fields[e][a:b] for e,p,a,b,c in records)
            return len(self.tok.encode(actual,add_special_tokens=False).ids)
        native_actual=surface(base)
        merged=flatten(state)
        merged_actual=surface(merged)
        assert merged_actual==spent
        fallback=spent>CAP or any(v[4]<=0 for v in merged)
        if fallback:
            # Preserve original order, representation and coordinates. No novel fill
            # is evaluated for a case that cannot adopt a sound canonical seed.
            orig_quote=[[*k,a,b,self.cost(k,a,b)] for k,a,b in (self.spans[n] for n in origin)]
            actual=surface(orig_quote)
            ok=actual<=CAP and all(x[4]>0 for x in orig_quote)
            chosen=orig_quote if ok else base
            return dict(skip=base,U=chosen,W=chosen,F=chosen),dict(fallback=True,infeasible=not ok,
                native_actual=native_actual,union_seed=merged_actual,whole_add=0,window_add=0,overlap_char=sum(b-a for v in raw.values() for a,b in v)-sum(b-a for v in canon.values() for a,b in v))
        arms=dict(skip=base,U=merged)
        def attempt(k,a,b):
            nonlocal spent
            old=state.get(k,[])
            if not list(gaps(a,b,old)):return False
            new=merge([*old,(a,b)])
            c=sum(self.cost(k,i,j) for i,j in new)
            cand=spent-by_field.get(k,0)+c
            if cand>CAP or c<=0 or any(self.cost(k,i,j)<=0 for i,j in new):
                return False
            state[k]=new;by_field[k]=c;spent=cand
            return True
        whole_add=0;window_add=0
        for nid in rank:
            if attempt(*self.spans[nid]):whole_add+=1
        whole={k:list(v) for k,v in state.items()}
        arms["W"]=flatten(whole)
        assert includes(canon,whole) and surface(arms["W"])==spent<=CAP
        query=set(content_tokens(self.q[row["q"]]))
        for nid in rank:
            if spent==CAP:break
            key,a,b=self.spans[nid];width=min(64,CAP-spent)
            candidates=[]
            for left,right in gaps(a,b,state.get(key,[])):
                for i,j in self.windows(key,left,right,width):
                    st=set(content_tokens(self.fields[key[0]][i:j]))
                    candidates.append((-len(query&st),i,j))
            for _,i,j in sorted(set(candidates)):
                if attempt(key,i,j):
                    window_add+=1;break
        arms["F"]=flatten(state)
        assert includes(whole,state) and surface(arms["F"])==spent<=CAP
        info=dict(fallback=False,infeasible=False,native_actual=native_actual,union_seed=merged_actual,whole_add=whole_add,window_add=window_add,
            overlap_char=sum(b-a for v in raw.values() for a,b in v)-sum(b-a for v in canon.values() for a,b in v))
        return arms,info


def shard(args):
    method,i=args
    model=load(ROOT/(method+"-plan.json"));rank=rankpath(method,i)
    assert model["ranks"][rank.name]==sha(rank)
    by_t=defaultdict(list)
    for row in load(rank):by_t[row["t"]].append(row)
    tok=Tokenizer.from_file(str(TOKENIZER));tok.no_padding();tok.no_truncation()
    rows=[];st=time.perf_counter();cpu=time.process_time()
    for t,queries in sorted(by_t.items()):
        project=load(CACHE/f"{i}-{t}.json.gz");assert project["t"]==t
        ep=Episode(project,tok)
        for q in queries:
            arms,info=ep.pack(q)
            rows.append(dict(q=q["q"],t=t,arms=arms,info=info))
    p=ROOT/f"{method}-pred-{i}.json.gz";put(p,rows)
    print(method,i,len(rows),round(time.perf_counter()-st,1),flush=True)
    return dict(file=p.name,sha=sha(p),n=len(rows),worker_seconds=time.perf_counter()-st,cpu=time.process_time()-cpu)


def predict(method):
    plan=load(ROOT/(method+"-plan.json"));design=load(ROOT/"design-lock.json")
    assert design["code"]==sha(ROOT/"pack.py") and design["native_tokenizer"]==sha(TOKENIZER)
    assert plan["design"]==sha(ROOT/"design-lock.json")
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as pool:
        info=list(pool.map(shard,[(method,i) for i in range(8)]))
    expect={r["query_id"] for r in load(OFF/"cohort.json")}
    actual=[r["q"] for entry in info for r in load(ROOT/entry["file"])]
    assert len(actual)==len(expect)==2000 and set(actual)==expect
    put(ROOT/f"{method}-forecast-seal.json",dict(ranks=plan["ranks"],plan=sha(ROOT/(method+"-plan.json")),shards=info,
        wall_seconds=time.perf_counter()-start,cpu_worker_seconds=sum(x["cpu"] for x in info)))


if __name__=="__main__":
    if sys.argv[1]=="design":common_plan()
    else:{"plan":model_plan,"predict":predict}[sys.argv[1]](sys.argv[2])
