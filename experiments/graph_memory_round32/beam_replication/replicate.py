"""Physical on-demand DeBERTa scoring with independent phases and resumable checkpoints."""
from pathlib import Path
import hashlib,json,sys,time,itertools
from collections import Counter
HERE=Path(__file__).resolve().parent
BEAM=HERE.parents[1]/"graph_memory_round31/hotpot_native"
sys.path.insert(0,str(BEAM))
from run import sha,read,put,BLIND,MODEL,load_model,inputs
PRIVATE=Path("D:/CodexResearch/x20-r32-beam")

def freeze():
    corpus=inputs();prior=read(BEAM/"plan.json")
    old=prior["panel"];eligible=[q for q,r in corpus.items() if len(r["titles"])==10 and q not in old]
    selected=sorted(eligible,key=lambda q:hashlib.sha256(("r32-native-replication/"+q).encode()).digest())[:64]
    assert len(selected)==64 and not set(selected)&set(old)
    plan={"code":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),"prior":sha(BEAM/"manifest.json"),
          "old":old,"panel":selected,"model":sha(MODEL),"data":sha(BLIND),"eligible":len(eligible)}
    if (HERE/"plan.json").exists():assert read(HERE/"plan.json")==plan
    else:put(HERE/"plan.json",plan)

def pool(order,removed):
    live=[d for d in order if d not in removed];roots=set(live[:2])
    return [p for p in itertools.combinations(sorted(live),2) if roots.intersection(p)]

def memoized_tree(order,score):
    visited=set();winners=set();trace=[]
    def visit(removed):
        if removed in visited:return
        visited.add(removed);edges=pool(order,removed)
        # Break true ties by oriented first/second corpus id, as in R31.
        w=min(edges,key=lambda p:(-score(p),orient(order,p)))
        winners.add(w);trace.append({"removed":sorted(removed),"winner":w,"edges":len(edges)})
        if len(removed)<2:
            for d in w:visit(removed|{d})
    visit(frozenset())
    return winners,trace

def orient(order,pair):
    a,b=pair
    return (a,b) if order.index(a)<order.index(b) else (b,a)

class Physical:
    def __init__(self,model,tok,record):
        import torch
        self.model=model;self.log=[];self.scores={}
        def tokenize(text,maximum):
            return tok.encode(text,add_special_tokens=False,truncation=True,max_length=maximum)
        q=tokenize(record["q"].removesuffix("?"),512)
        docs=[tokenize(title+"".join(content),512-len(q)) for title,content in zip(record["titles"],record["sentences"])]
        allowance=(510-len(q))//2
        self.qdoc=[(q+d)[:510-allowance] for d in docs];self.docs=docs
        self.cls_id=tok.cls_token_id;self.sep_id=tok.sep_token_id
        self.first=[self.evaluate(ids,False,"hop1",idx) for idx,ids in enumerate(self.qdoc)]
        assert len(set(self.first))==len(self.first),"true first-hop tie requires author tie behavior"
        self.order=sorted(range(len(self.first)),key=lambda i:(-self.first[i],i))
    def evaluate(self,ids,pair,phase,key):
        import torch
        started=time.perf_counter()
        z=torch.tensor([[self.cls_id,*ids,self.sep_id]],dtype=torch.long)
        mask=torch.ones_like(z);mask[0,-1]=0
        with torch.inference_mode():
            cls=self.model.encoder(input_ids=z,attention_mask=mask)[0][:,0,:]
            head=self.model.hop_n_classifier_layer if pair else self.model.hop_classifier_layer
            value=float(head(cls)[0,1])
        self.log.append([phase,key,z.shape[1],time.perf_counter()-started])
        return value
    def get(self,pair,phase):
        if pair not in self.scores:
            a,b=orient(self.order,pair)
            ids=(self.qdoc[a]+self.docs[b])[:510]
            self.scores[pair]=self.evaluate(ids,True,phase,pair)
        return self.scores[pair]

def run_case(model,tok,record):
    scorer=Physical(model,tok,record);order=scorer.order
    winners,trace=memoized_tree(order,lambda pair:scorer.get(pair,"lazy"))
    active=set(scorer.scores)
    keys=list(itertools.combinations(sorted(order),2));first4=set(order[:4])
    pool4=[p for p in keys if first4.intersection(p)]
    assert active<=set(pool4) and len(pool4)==30
    for p in pool4:scorer.get(p,"pool4_remainder")
    for p in keys:scorer.get(p,"full_remainder")
    ranked=sorted(keys,key=lambda p:(-scorer.scores[p],orient(order,p)))
    assert len(scorer.log)==55
    return {"first":scorer.first,"order":order,"rows":[[*p,scorer.scores[p]] for p in ranked],"winners":[p for p in ranked if p in winners],
        "trace":trace,"calls":scorer.log,"unique_lazy_pairs":len(active),"uncached_tree_pair_calls":sum(x["edges"] for x in trace)}

def parity(q,v):
    f=read(BEAM/"forecasts"/(q+".json"))["full"];order=v["order"]
    old=[tuple(sorted(row[:2])) for row in f["pairs"]];new=[tuple(row[:2]) for row in v["rows"]]
    old_scores={tuple(sorted(row[:2])):row[2] for row in f["pairs"]}
    assert f["doc_order"]==order
    disagree=0;tree_disagree=0
    tree=list(map(tuple,v["winners"]))
    for k in range(3):
        for banned in itertools.combinations(order,k):
            eligible=set(pool(order,set(banned)))
            w=next(p for p in old if p in eligible);new_w=next(p for p in new if p in eligible)
            disagree+=int(w!=new_w);tree_disagree+=int(w!=next(p for p in tree if p in eligible))
    return {"questions":1,"states":56,"source_45_same_order":old==new,"score_rank_mismatches":sum(a!=b for a,b in zip(old,new)),
            "max_pair_abs":max(abs(row[2]-old_scores[tuple(row[:2])]) for row in v["rows"]),
            "dynamic_disagree":disagree,"lazy_tree_disagree":tree_disagree,"unique_pair_calls":v["unique_lazy_pairs"]}

def run():
    import psutil,torch
    plan=read(HERE/"plan.json");assert plan["code"]==sha(Path(__file__)) and plan["model"]==sha(MODEL) and plan["data"]==sha(BLIND)
    private=PRIVATE/sha(HERE/"plan.json");private.mkdir(exist_ok=True,parents=True)
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    proc=psutil.Process()
    if hasattr(psutil,"BELOW_NORMAL_PRIORITY_CLASS"):proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    model,tok,invocations=load_model();corpus=inputs()
    controls={}
    for stage in ("old","panel"):
        dest=private/stage;dest.mkdir(exist_ok=True)
        for idx,q in enumerate(plan[stage]):
            out=dest/(q+".json")
            if not out.exists():
                invocations.clear();t=time.perf_counter()
                row=run_case(model,tok,corpus[q]);row.update(q=q,plan=sha(HERE/"plan.json"),wall=time.perf_counter()-t,encoder_calls=len(invocations))
                assert len(invocations)==55
                put(out,row)
            else:
                row=read(out);assert row["q"]==q and row["plan"]==sha(HERE/"plan.json")
            if stage=="old":controls[q]=parity(q,row)
            print(stage,idx+1,"/",len(plan[stage]),flush=True)
        if stage=="old":
            put(HERE/"old-parity.json",controls)
            assert all(r["dynamic_disagree"]==r["lazy_tree_disagree"]==0 for r in controls.values())
    import gzip
    allrows={q:read(private/"panel"/(q+".json")) for q in plan["panel"]}
    raw=json.dumps(allrows,sort_keys=True,separators=(",",":")).encode()
    out=HERE/"forecasts.json.gz";tmp=private/"package-ready.tmp"
    tmp.write_bytes(gzip.compress(raw,mtime=0));tmp.replace(out)
    put(HERE/"forecast-seal.json",{"plan":sha(HERE/"plan.json"),"forecasts":sha(out),"parity":sha(HERE/"old-parity.json"),"n":len(allrows)})
if __name__=="__main__":
    if sys.argv[1]=="freeze":freeze()
    else:run()
