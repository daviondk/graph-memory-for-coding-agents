"""Update previously retained evidence only when a matching call-side arrives."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip,json,math,os,sys
from pathlib import Path
for k in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19";C=D.parent/"set_writer"
sys.path.insert(0,str(OLD/"write_learned"));from features import stream,rows,design,tool_lookup,load,save,sha
import numpy as np
def parts(base,raw):
    # Evaluation adapter: group already completed event payloads by chronological address.
    groups=defaultdict(list);parents=defaultdict(dict)
    for j,(e,a,b,c,n) in enumerate(base["blocks"]):groups[e].append((j,a,b,c))
    for src in raw["pool"]:
        s=src["source_spans"][0];m=src["metadata"];eid=s["event_id"]
        parents[eid][m["chunk_index"]]=(s["char_start"],s["char_end"],m["call_id"],m["node_kind"])
    for e,(eid,ptr) in enumerate(base["addresses"]):
        candidate=sorted(parents[eid].items());n=len(candidate);call=candidate[0][1][2]
        out=ptr=="/content";assert all(v[2]==call and (v[3]=="content.tool_output")==out for _,v in candidate)
        pieces=[]
        for j,a,b,c in groups[e]:
            parent=next((i for i,(l,h,_,_) in candidate if l<=a and b<=h),None)
            pieces.append((j,parent,c))
        yield e,eid,call,out,n,pieces

def select(base,raw,linear,coef):
    arms={};blocks=base["blocks"]
    for arm in ("live","static","adjacent"):
        active={};stored=0;changes=0;maxlive=0
        def priority(j,p,side,n,opp,tie):
            if p is None:bonus=0
            else:
                bonus=(int(p<n-1)*coef[0]+int(p>0)*coef[1])*math.log(2)
                if arm!="adjacent":bonus+=math.log1p(opp)*coef[3 if side else 2]
            return (-(linear[j]+bonus),tie,j)
        for e,eid,call,out,n,pieces in parts(base,raw):
            partners=[j for j,(_,other,side,p,size,score_tie) in active.items() if call is not None and other==call and out!=side and p is not None]
            partner_count=len({active[j][3] for j in partners})
            if arm=="live":
                for j in partners:
                    pr,cc,side,p,size,tie=active[j];new=priority(j,p,side,size,n,tie)
                    changes+=pr!=new;active[j]=(new,cc,side,p,size,tie)
            tie=stream.stable(eid)
            for j,p,c in pieces:
                active[j]=(priority(j,p,out,n,partner_count,tie),call,out,p,n,tie);stored+=c
                while stored>8192:
                    bad=max(active,key=lambda k:active[k][0]);stored-=blocks[bad][3];del active[bad]
                maxlive=max(maxlive,len(active));assert stored<=8192
        arms[arm]=(sorted(active),changes,maxlive)
    return arms
def input_paths(stage,i):
    return ((OLD/f"online_write/forecast-{i}.jsonl.gz",OLD/f"write_learned/forecast-{i}.jsonl.gz",stream.CACHE) if stage=="test" else (OLD/f"write_transfer/predictions-{i}.jsonl.gz",OLD/f"write_learned/transfer-dev-{i}.jsonl.gz",Path("D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection")))
def shard(job):
    stage,i=job;src,ref,cache=input_paths(stage,i);writer=load(OLD/"write_learned/model.json");m=writer["arms"]["full"];prior=load(D.parent/"factor_reader/prior.json")["models"]["degree"];coef=prior["coef"];assert len(coef)==8
    dest=D/f"{stage}-decisions-{i}.jsonl.gz";diag=[]
    with gzip.open(src,"rb") as source,gzip.open(ref,"rb") as rref,gzip.open(dest,"wt",encoding="utf8",compresslevel=3) as fo:
        for ln,pr in zip(source,rref,strict=True):
            base=json.loads(ln);old=json.loads(pr);t=base["t"];assert t==old["t"];r=load(cache/f"{i}-{t}.json.gz");ad,bl=base["addresses"],base["blocks"]
            x,n=rows(ad,bl,r["fields"],tool_lookup(r["pool"]));z=(design(x,n,writer["tools"],True)-m["means"])/m["scale"]
            linear=z@np.array(m["coefficients"])+m["intercept"];prob=1/(1+np.exp(-np.clip(linear,-700,700)))
            cost=[b[3] for b in bl];ties=[stream.stable(eid) for eid,_ in ad];baseline=stream.select(cost,[((-float(v),ties[b[0]]),) for b,v in zip(bl,prob)],0,8192)
            opts=select(base,r,linear,coef);opts["frozen"]=(baseline,0,0)
            q=[(qid,stream.content_tokens(s)) for qid,s in r["q"]];lex=[stream.content_tokens(r["fields"][ad[e][0]][a:b]) for e,a,b,c,_ in bl]
            picks={a:[keep,stream.read(keep,cost,lex,q)] for a,(keep,_,_) in opts.items()};assert picks["frozen"]==old["a"]["tokens/full"][:2]
            diag.append({"t":t,"live_priority_updates":opts["live"][1],"peak_live_blocks":opts["live"][2],"retained_differs":opts["live"][0]!=baseline})
            fo.write(json.dumps({"t":t,"a":picks},separators=(",",":"))+"\n")
    save(D/f"{stage}-activity-{i}.json.gz",diag);return sha(dest)
if __name__=="__main__":
    stage=sys.argv[1]
    with ProcessPoolExecutor(2) as pool:hs=list(pool.map(shard,[(stage,i) for i in range(8)]))
    save(D/(stage+"-seal.json"),{"model":sha(D.parent/"factor_reader/prior.json"),"writer":sha(OLD/"write_learned/model.json"),"code":sha(D/"policy.py"),"protocol":sha(D/"PROTOCOL_RU.md"),"files":{f"{stage}-decisions-{i}.jsonl.gz":h for i,h in enumerate(hs)}})
