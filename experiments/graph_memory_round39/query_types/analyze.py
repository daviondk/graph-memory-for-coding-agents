"""Post-hoc strata of fixed query-level outcomes using original authored types and source fields."""
from pathlib import Path
import gzip,hashlib,json,os
for key in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS"):os.environ[key]="1"
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1];GLOBAL=D.parent/"global_packet";TAIL=D.parent/"remaining_budget"
QUERY=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl.metadata.jsonl")
GOLD=W/"graph_memory_round18/isetrace_official/gold-spans.json.gz"
SEEDS=(13,17,29,37,41)
def read(p):
    data=p.read_bytes();return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    data=(json.dumps(obj,separators=(",",":"),allow_nan=False,sort_keys=True)+"\n").encode();data=gzip.compress(data,mtime=0) if p.suffix==".gz" else data
    if p.exists():assert p.read_bytes()==data
    else:p.write_bytes(data)

def label():
    labels={x["query_id"]:x for x in map(json.loads,QUERY.open(encoding="utf8"))};gold=read(GOLD)
    split=read(W/"graph_memory_round22/native_multiseed/official580/split.json.gz")["test"];recs={}
    for row in split:
        q=row["q"];v=labels[q];assert v["trajectory_id"]==row["t"]
        spans=gold[q];events={r["event_id"] for r in spans};fields={(r["event_id"],r["json_pointer"]) for r in spans}
        recs[q]=dict(t=row["t"],kind=v["memory_mode"],events=len(events),fields=len(fields))
    assert sorted(sum(r["kind"]==k for r in recs.values()) for k in {r["kind"] for r in recs.values()})==[453,641,906]
    save(D/"strata.json.gz",recs);save(D/"strata-seal.json",dict(rows=sha(D/"strata.json.gz"),meta=sha(QUERY),gold=sha(GOLD),protocol=sha(D/"PROTOCOL_RU.md")))

def analyze():
    rec=read(D/"strata.json.gz");assert sha(D/"strata.json.gz")==read(D/"strata-seal.json")["rows"]
    q=sorted(rec);groups,idx=np.unique([rec[k]["t"] for k in q],return_inverse=True)
    features=[rec[k] for k in q];modes={m:np.asarray([v["kind"]==m for v in features]) for m in ("direct_recall","linked_recall","multi_fact_recall")}
    ev=np.array([v["events"] for v in features]);fs=np.array([v["fields"] for v in features])
    masks={**modes,"one_event":ev==1,"two_events":ev==2,"three_plus_events":ev>=3,"multiple_events":ev>=2,"one_field":fs==1,"multiple_fields":fs>=2}
    contrast={};examples={};refs={}
    for seed in SEEDS:
        gp=read(GLOBAL/f"test-{seed}-pred.json.gz");go=read(GLOBAL/f"test-{seed}-outcomes.json.gz");baseline=read(TAIL/f"test-{seed}-outcomes.json.gz");bp=read(TAIL/f"test-{seed}-pred.json.gz")
        assert all(set(a)==set(q) for a in [gp,go,baseline,bp])
        for folder in [GLOBAL,TAIL]:
            for suf in ("scores.json","seal.json"):
                p=folder/f"test-{seed}-{suf}";refs[str(p.relative_to(D.parent))]=sha(p)
        for rd in ("R35","wo_chunk_adjacency"):
            values=[];extra=[]
            for k in q:
                own=gp[k][1]["graph-dp"];obj=bp[k][1][rd];ref=obj["head"]+obj["extra"]["firstfit"]
                a=go[k][1]["graph-dp"];b=baseline[k][1][rd]["firstfit"]
                assert gp[k][0]==go[k][0]==baseline[k][0]==rec[k]["t"]
                x,y=set(own),set(ref);values.append([*a,*b,len(x-y),len(y-x),int(x!=y),int(a[0]>b[0]),int(a[0]<b[0])])
            contrast.setdefault(rd,[]).append(np.asarray(values))
    keys=list(masks);results={}
    weights=np.stack([np.bincount(idx,weights=masks[k].astype(int),minlength=len(groups)) for k in keys],axis=1)
    for rd,m in contrast.items():
        arr=np.stack(m);delta=arr[:,:,:4]-arr[:,:,4:8];cl=np.zeros((len(groups),len(SEEDS),len(keys)))
        for j,k in enumerate(keys):
            np.add.at(cl[:,:,j],idx,delta[:,:,0].T*masks[k][:,None])
        rng=np.random.default_rng(39185);boots=[]
        for _ in range(100):
            draws=rng.integers(len(groups),size=(100,len(groups)));cnt=np.stack([np.bincount(r,minlength=len(groups)) for r in draws])
            v=(cnt@cl.reshape(len(groups),-1)).reshape(100,len(SEEDS),len(keys))/(cnt@weights)[:,None,:]
            seed_ix=rng.integers(0,len(SEEDS),size=(100,len(SEEDS)));boots.append(v[np.arange(100)[:,None],seed_ix].mean(axis=1))
        boot=np.vstack(boots);result={}
        for j,k in enumerate(keys):
            subset=arr[:,masks[k]];result[k]=dict(n=int(masks[k].sum()),means=subset.mean(axis=(0,1)).tolist(),delta=delta[:,masks[k]].mean(axis=(0,1)).tolist(),
                fs_ci95=np.quantile(boot[:,j],[.025,.975]).tolist(),wins=int(subset[:,:,11].sum()),losses=int(subset[:,:,12].sum()))
        interactions={}
        for a,b in (("multi_fact_recall","direct_recall"),("multiple_events","one_event")):
            s=boot[:,keys.index(a)]-boot[:,keys.index(b)];interactions[a+" minus "+b]=dict(delta=result[a]["delta"][0]-result[b]["delta"][0],ci95=np.quantile(s,[.025,.975]).tolist())
        results[rd]=dict(groups=result,interactions=interactions)
    save(D/"results.json",dict(contrasts=results,upstream=refs,labels=sha(D/"strata.json.gz"),means_columns=["proposed_fs","proposed_cov","proposed_tokens","proposed_n","base_fs","base_cov","base_tokens","base_n","added","removed","changed","win","loss"],code=sha(D/"analyze.py")))
    print({rd:x["interactions"] for rd,x in results.items()})
if __name__=="__main__":
    import sys
    {"label":label,"analyze":analyze}[sys.argv[1]]()

