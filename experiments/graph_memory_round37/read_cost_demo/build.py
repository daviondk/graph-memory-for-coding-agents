"""Compile a network-independent teaching artifact from frozen numeric reads."""
from pathlib import Path
import gzip,json,hashlib,sys
D=Path(__file__).resolve().parent;W=D.parents[1];EXT=D.parent/"external_budget";R=W/"graph_memory_round34/external_transfer";S=R/"strong";PUB=W/"memory_session5/serbench/upstream";sys.path.insert(0,str(PUB/"src"));from serbench import _reference_scorer as scorer
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    b=(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def main():
    p=EXT/"manifest.json";assert sha(p)=="605498889c097560363b7feaf3511060ddfdbc49b32a8895dbcb55de65b5ca20"
    for name,h in read(p)["files"].items():assert sha(EXT/name)==h
    src=read(EXT/"plan.json");assert sha(R/"manifest.json")==src["source_manifest"]
    for n,h in src["inputs"].items():assert sha(R/n)==h
    ids=[next(x["q"] for x in read(EXT/"quota-examples.json")["win_finite_both_multigroup_by_budget"]["2048"] if x["rank_same"]),read(EXT/"results.json")["mechanism"]["examples"]["rank8_win"]["q"]];assert len(set(ids))==2
    dat=read(S/"features.json.gz");pred=read(S/"test-ranks.json.gz");rows=read(EXT/"thresholds.json.gz");expected={};cases=[];audit={}
    lab=PUB/"data/cal500/labels.jsonl.gz";assert sha(lab)==src["gold"] and sha(Path(scorer.__file__))==src["scorer"]
    with gzip.open(lab,"rt",encoding="utf8") as rf:gold={v["state_id"]:v for v in map(json.loads,rf) if v["state_id"] in ids}
    for k,q in enumerate(ids,1):
        r=dat[q]; assert r["split"]=="test";g=gold[q];z=rows[q];srcids=r["ids"];groups=g["required_evidence_groups"];alts=g["alternative_minimal_sets"];anon={v:i+1 for i,v in enumerate(srcids)};N=20;methods=["dense_state","union_cost"]
        indices=[pred[q][m][:N] for m in methods];assert all(len(ix)==N for ix in indices);used=sorted(set(indices[0])|set(indices[1]));entries={anon[srcids[j]]:{"cost":r["qw"][j],"g":[i for i,y in enumerate(groups) if srcids[j] in y["acceptable_evidence_ids"]],"a":[i for i,y in enumerate(alts) if srcids[j] in y]} for j in used}
        rows_out=[[anon[srcids[j]] for j in ix] for ix in indices];c={"id":k,"maxRank":N,"groups":[v["minimum_required"] for v in groups],"alts":[len(set(y)) for y in alts],"items":entries,"orders":rows_out,"defaultB":[2048,6144][k-1],"defaultK":8}
        cases.append(c);exp=[];old=scorer.ideal_group_dcg;memo={}
        def cached(gs,w,depth):
            if depth not in memo:memo[depth]=old(gs,w,depth)
            return memo[depth]
        scorer.ideal_group_dcg=cached
        try:
            for m,ix in zip(methods,indices):
                evals=[];cost=0;order=[srcids[j] for j in ix]
                for d in range(N+1):
                    if d:cost+=r["qw"][ix[d-1]]
                    value=scorer.score_prediction(order[:d],g,20);grec=value["group_recall@20"];hits=[scorer.group_completion_rank(order[:d],v,20) is not None for v in groups]
                    assert abs(sum(hits)/len(groups)-grec)<1e-12
                    evals.append({"spent":cost,"complete":bool(value["mss_complete@20"]),"groups":hits})
                t=next(i for i,v in enumerate(evals) if v["complete"]);assert(t,evals[t]["spent"])==(z["arms"][m]["rank_full"],z["arms"][m]["cost_full"])
                assert [entries[anon[srcids[j]]]["cost"] for j in ix[:8]]==[v[1] for v in z["arms"][m]["head"]]
                for bi,budget in enumerate((512,1024,2048,4096,6144,8192)):
                    depth=max(j for j in range(9) if evals[j]["spent"]<=budget);v=evals[depth];base=z["arms"][m]["budgets"][bi]
                    assert [int(v["complete"]),sum(v["groups"])/len(groups),v["spent"],depth]==[base[0],base[1],base[4],base[5]]
                exp.append(evals)
        finally:scorer.ideal_group_dcg=old
        expected[str(k)]=exp;audit[str(k)]={"state_fingerprint":hashlib.sha256(q.encode()).hexdigest(),"candidate_pool":len(srcids),"shown_candidate_count":len(used),"prefixes_checked":2*(N+1)}
    packed=json.dumps(cases,sort_keys=True,separators=(",",":"));html=(D/"template.html").read_text(encoding="utf8").replace("__NUMERIC_CASES__",packed);assert "__NUMERIC_CASES__" not in html
    (D/"index.html").write_text(html,encoding="utf8");save(D/"oracle.json",expected);save(D/"source.json",{"source_manifest":sha(p),"raw_scorer":src["scorer"],"html":sha(D/"index.html"),"oracle":sha(D/"oracle.json"),"template":sha(D/"template.html"),"build":sha(D/"build.py"),"cases":audit})
if __name__=="__main__":main()
