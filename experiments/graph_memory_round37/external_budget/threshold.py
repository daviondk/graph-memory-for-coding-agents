"""Audit registered readout using frozen ranks; do not execute any corpus text."""
from pathlib import Path
from collections import Counter
import gzip,json,hashlib,sys
from functools import lru_cache
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round34/external_transfer";S=R/"strong";SER=W/"memory_session5/serbench";UP=SER/"upstream";PUB=UP/"data/cal500"
sys.path.insert(0,str(UP/"src"));from serbench import _reference_scorer as scorer
METHODS=("dense_state","union_cost","equal_neg_weights","no_edges");BUD=(512,1024,2048,4096,6144,8192)
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,z):
    b=(json.dumps(z,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def goldrows(p,wanted):
    with gzip.open(p,"rt",encoding="utf8") as f:
        for line in f:
            j=json.loads(line)
            if j["state_id"] in wanted:yield j
def setup():
    files=load(R/"manifest.json");rels=["strong/features.json.gz","strong/test-ranks.json.gz","strong/test-outcomes.json.gz","strong/results.json","strong/selection.json","strong/models.json","strong/seal.json","ablation-ranks.json.gz","ablation-outcomes.json.gz","ablation-seal.json","input.json"]
    for f in rels:assert files[f]==sha(R/f)
    meta=load(R/"input.json");prev=load(S/"results.json");assert sha(PUB/"labels.jsonl.gz")==prev["gold"] and sha(Path(scorer.__file__))==prev["scorer"]
    plan={"protocol":sha(D/"PROTOCOL_RU.md"),"source_manifest":sha(R/"manifest.json"),"inputs":{f:files[f] for f in rels},"scorer":prev["scorer"],"gold":prev["gold"],"budgets":BUD,"arm_order":METHODS,"program":sha(D/"threshold.py")}
    save(D/"plan.json",plan);return meta
def validate_tokens(data,pred,meta):
    from tokenizers import Tokenizer
    wp=Path("D:/CodexResearch/x20-isetrace-runtime/e5-base-v2/tokenizer.json");qw=SER.parent/"packets/qwen_tokenizer.json";assert sha(wp)==meta["sources"][wp.name] and sha(qw)==meta["sources"][qw.name]
    tok=[Tokenizer.from_file(str(p)) for p in (wp,qw)]
    for t in tok:t.no_truncation();t.no_padding()
    @lru_cache(24000)
    def cost(s):return tuple(len(t.encode(s,add_special_tokens=False).ids) for t in tok)
    wanted=set(pred);checked=0;tags=set();assert sha(PUB/"items.jsonl.gz")==meta["sources"]["items.jsonl.gz"]
    for qraw in goldrows(PUB/"items.jsonl.gz",wanted):
        q=qraw["state_id"];r=data[q];assert r["task"]==qraw["instance_id"] and r["task"] not in meta["excluded_tasks"];tags.add(q)
        for j,c in enumerate(sorted(qraw["candidate_evidence"],key=lambda v:v["evidence_id"])):
            serial=str(c.get("source_path") or "")+"\n"+str(c.get("content_excerpt") or "")+"\n\n";w,z=cost(serial);assert r["ids"][j]==c["evidence_id"] and w==r["wp"][j] and z==r["qw"][j];checked+=1
    assert wanted==tags;return checked
def first_where(order,options,req):
    if req==0:return 0
    hit=[i for i,j in enumerate(order,1) if j in options];return hit[req-1] if len(hit)>=req else None
def total_groups(ranks,n):return sum(i is not None and i<=n for i in ranks)
def prefix(ordered,price,budget):
    cost=0;n=0
    for idx in ordered[:8]:
        if cost+price[idx]>budget:break
        cost+=price[idx];n+=1
    return n,cost
def process(q,row,order,g,prior,calls):
    ids=row["ids"];n=len(ids);assert sorted(order)==list(range(n)) and n>=8;loc={k:i for i,k in enumerate(ids)}
    groups=[{loc[x] for x in a["acceptable_evidence_ids"] if x in loc} for a in g["required_evidence_groups"]];req=[a.get("minimum_required",1) for a in g["required_evidence_groups"]];alts=[a for a in g["alternative_minimal_sets"]];group_r=[first_where(order,opts,quota) for opts,quota in zip(groups,req)]
    alt_r=[first_where(order,{loc[x] for x in a if x in loc},len(set(a))) if set(a)<=set(loc) else None for a in alts]
    def complete(j):
        gr=total_groups(group_r,j)==len(groups);al=any(v is not None and v<=j for v in alt_r);return gr or al,gr,al
    anycert=set().union(*groups,*[{loc[x] for x in a if x in loc} for a in alts])
    nf=next((k for k in range(n+1) if complete(k)[0]),None);assert nf is None or complete(nf)[0] and (nf==0 or not complete(nf-1)[0])
    ts=[row["qw"][i] for i in order];assert all(y>0 for y in ts)
    nw=row["wp"];qw=row["qw"];free=[v if i in anycert else 0 for i,v in enumerate(qw)];grp=[];official={}
    for k in range(9):
        v=scorer.score_prediction([ids[j] for j in order[:k]],g,8);co,gr,al=complete(k);grec=total_groups(group_r,k)/len(groups) if groups else 1.
        assert int(co)==v["mss_complete@8"] and abs(grec-v["group_recall@8"])<1e-11;official[k]=[int(co),float(grec)];calls["prefix_native"]+=1
    c8=nf if nf is not None and nf<=8 else None;t8=sum(ts[:c8]) if c8 is not None else None;cf=sum(qw[i] for i in order[:c8] if i in anycert) if c8 is not None else None
    states=[]
    for B in BUD:
        k,paid=prefix(order,qw,B);kfree,_=prefix(order,free,B);co,gc,ac=complete(k);grhits=total_groups(group_r,k)
        states.append([int(co),grhits/len(groups) if groups else 1.,int(gc),int(ac),paid,k,int(complete(kfree)[0])]);assert int(co)==int(t8 is not None and t8<=B)
    warr,_=prefix(order,nw,2048);ow=scorer.score_prediction([ids[i] for i in order[:warr]],g,8)["mss_complete@8"];f5=scorer.score_prediction([ids[j] for j in order[:5]],g,5)["mss_complete@5"]
    assert [states[4][0],f5,official[8][0],official[8][1],ow]==prior[:5] and states[4][4:6]==prior[5:7];calls["native_historical_coordinates"]+=7
    # Public rank positions, certificate group indices and token prices suffice to inspect a representative state.
    heads=[[i+1,ts[i],[(j+1) for j,opts in enumerate(groups) if order[i] in opts],[(j+1) for j,a in enumerate(alts) if ids[order[i]] in a],int(order[i] in anycert)] for i in range(8)]
    return {"rank_full":nf,"cost_full":sum(ts[:nf]) if nf is not None else None,"rank8":c8,"cost8":t8,"cert_eligible_tokens":cf,"outside_tokens":(t8-cf) if t8 is not None else None,"group_ranks":group_r,"alternate_ranks":alt_r,"head":heads,"budgets":states,"uncapped8":official[8]}
def main():
    meta=setup();data=load(S/"features.json.gz");old=load(S/"test-outcomes.json.gz");ab=load(R/"ablation-outcomes.json.gz");pr=load(S/"test-ranks.json.gz");abpr=load(R/"ablation-ranks.json.gz");eligible=set(pr)
    assert set(pr)==set(abpr)==set(old)==set(ab)=={q for q,z in data.items() if z["split"]=="test"};rep={s:{r["repo"] for r in data.values() if r["split"]==s} for s in ["train","dev","test"]};tasks={s:{r["task"] for r in data.values() if r["split"]==s} for s in rep}
    assert all(not(rep[a]&rep[b] or tasks[a]&tasks[b]) for a,b in [("train","dev"),("train","test"),("dev","test")]);assert len(eligible)==214 and len(rep["test"])==69;tok=validate_tokens(data,pr,meta)
    native=scorer.ideal_group_dcg;out={};cnt=Counter()
    for g in goldrows(PUB/"labels.jsonl.gz",eligible):
        q=g["state_id"];cache={};z=data[q]
        def memo(gs,w,k):
            if k not in cache:cache[k]=native(gs,w,k)
            return cache[k]
        scorer.ideal_group_dcg=memo
        try:
            arms={}
            for m in METHODS:
                fore=pr[q][m] if m in METHODS[:2] else abpr[q][m];pre=(old[q] if m in METHODS[:2] else ab[q])["arms"][m]
                arms[m]=process(q,z,fore,g,pre,cnt)
        finally:scorer.ideal_group_dcg=native
        out[q]={"repo":z["repo"],"task":z["task"],"group_quota":[int(y.get("minimum_required",1)) for y in g["required_evidence_groups"]],"alt_sizes":[len(v) for v in g["alternative_minimal_sets"]],"arms":arms}
    assert len(out)==len(pr);save(D/"thresholds.json.gz",out);save(D/"audit.json",{"registered":sha(D/"plan.json"),"thresholds":sha(D/"thresholds.json.gz"),"native":dict(cnt),"candidate_costs_checked_both_tokenizers":tok,"splits":{s:{"repos":len(rep[s]),"tasks":len(tasks[s]),"states":sum(z["split"]==s for z in data.values())} for s in rep},"filtered_states":meta["excluded_states"],"filtered_tasks":len(meta["excluded_tasks"]),"distinct_eligible_repos":len(rep["test"])});print(dict(cnt),tok,len(out),flush=True)
if __name__=="__main__":main()
