"""Native ISETrace span scores, independent interval audit and paired cluster intervals."""
from collections import defaultdict
from pathlib import Path
from statistics import mean,median
import gzip
import json
import sys
D=Path(__file__).resolve().parent;OLD=D.parent/"graph_memory_round19"
sys.path.insert(0,str(OLD/"tail_read"))
from tail import pilot, compare, independent, load, OFF
from statistics import quantiles
from hashlib import file_digest
def save(path,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()+b"\n"
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix==".gz" else b)

def evaluate(category,experiment=""):
    folder=D/category
    base=experiment+"-" if experiment else ""
    seal=load(folder/(base+"forecast-seal.json"))
    for n,h in seal["files"].items():assert pilot.sha(folder/n)==h
    gold=load(OFF/"gold-spans.json.gz");cohort={r["query_id"]:r["trajectory_id"] for r in load(OFF/"cohort.json")}
    if category in ("fine_train","fine_lextrain","fine_subset") and experiment=="dev":
        cohort={r["q"]:r["t"] for r in load(OLD/"trained_rank/split.json.gz")["dev"]}
        gold={q:g for q,g in load(OLD/"write_transfer/gold-spans.json.gz").items() if q in cohort}
        assert set(gold)==set(cohort) and len(cohort)==500
    arms=defaultdict(dict); extra=[];changed=defaultdict(int)
    def assess(t,q,arm,selected):
        assert q in gold and cohort[q]==t and q not in arms[arm]
        truth=tuple(pilot.SourceSpan.model_validate(s) for s in gold[q])
        cost=sum(n.token_count for n in selected);assert cost<=2048
        met=pilot.span_metrics_under_token_budget(tuple(selected),truth,2048)
        alt=independent(gold[q],[n.model_dump() for n in selected])
        assert all(abs(v-getattr(met,k))<1e-12 for v,k in zip(alt,("coverage","density","full_support"),strict=True))
        arms[arm][q]=dict(t=t,tokens=cost,**{k:getattr(met,k) for k in ("full_support","coverage","density","f1")})
    def node(key,addr,item):
        e,a,b,c=item[:4];eid,ptr=addr[e]
        return pilot.RankedNodeRecord(node_id=str(key),score=0,token_count=c,source_spans=(pilot.SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b),))
    for i,n in enumerate(sorted(seal["files"])):
        if category=="online_update":
            with gzip.open(folder/n,"rb") as reads,gzip.open(OLD/"online_write"/f"forecast-{i}.jsonl.gz","rb") as src:
                for left,right in zip(reads,src,strict=True):
                    forecast,rec=json.loads(left),json.loads(right);t=rec["t"];assert forecast["t"]==t
                    nodes=[node(j,rec["addresses"],item) for j,item in enumerate(rec["blocks"])]
                    for arm,(keep,by_q,stats) in forecast["a"].items():
                        for q,take in by_q.items():
                            assert set(take)<=set(keep) and len(take)==len(set(take))
                            assess(t,q,arm,[nodes[j] for j in take])
                        extra.append(dict(t=t,arm=arm,stats=stats,stored_tokens=sum(nodes[j].token_count for j in keep)))
                        changed[arm]+=keep!=forecast["a"]["frozen"][0]
        else:
            for rec in load(folder/n):
                nodes={k:node(k,rec["addresses"],v) for k,v in rec["used"].items()}
                for q,by_arm in rec["picks"].items():
                    for arm,ids in by_arm.items():
                        assert len(ids)==len(set(ids));assess(rec["t"],q,arm,[nodes[k] for k in ids])
    for rs in arms.values():assert set(rs)==set(gold) and len(gold)==len(cohort)
    pairs=(("real","frozen"),("real","placebo"),("placebo","frozen")) if category=="online_update" else [(k,"skip") for k in arms if k!="skip"]+[("ratio","nog"),("ratio","rrf"),("ratio","prob")]
    summary={k:{f:mean(v[f] for v in rs.values()) for f in ("full_support","coverage","density","f1","tokens")}|{"hits":sum(bool(v["full_support"]) for v in rs.values())} for k,rs in arms.items()}
    result={"n":len(gold),"trajectories":len(set(cohort.values())),"summary":summary,"pairs":{a+"-"+b:compare(arms[a],arms[b]) for a,b in pairs}}
    if extra:
        save(folder/"activity.json.gz",extra)
        result["changed_archives"]=dict(changed)
        result["activity"]={a:{"any_promotions":sum(r["stats"][1]>0 for r in extra if r["arm"]==a),
            "total_promotions":sum(r["stats"][1] for r in extra if r["arm"]==a),"mean_peak_keys_bytes":mean(r["stats"][4] for r in extra if r["arm"]==a),
            "mean_peak_postings":mean(r["stats"][3] for r in extra if r["arm"]==a)} for a in arms}
    save(folder/(base+"outcomes.json.gz"),arms);save(folder/(base+"results.json"),result)
    print({a:(v["hits"],round(100*v["coverage"],2),round(v["tokens"])) for a,v in summary.items()},flush=True)
if __name__=="__main__":evaluate(*sys.argv[1:])
