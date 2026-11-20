"""Verify all later-release IDs, project disjointness, gold ranks and mixture scores, plus 48 fresh predictions."""
import json,gzip,pickle,hashlib
from collections import Counter,defaultdict
from transfer import D, read, save, sha, np, pq, load_gz, ARMS, compute, summary, panels
def main():
    train_repos={r[1].casefold() for p in panels() for r in load_gz(D/"cache"/(p.stem+".jsonl.gz"))}
    train_hash={r[2] for p in panels() for r in load_gz(D/"cache"/(p.stem+".jsonl.gz"))}
    pred={(fn,i):(repo,h,g,ranks) for fn,i,repo,h,ln,lens,g,ranks in load_gz(D/"transfer_predictions.jsonl.gz")}
    roster={(fn,i) for s,fn,i,repo,h,ln in read("transfer_roster.json")};assert set(pred)==roster
    spot=set(sorted(pred,key=lambda k:hashlib.sha256(repr(k).encode()).hexdigest())[:48])
    with (D/"experts.pkl").open("rb") as f:experts,gate=pickle.load(f)
    with (D/"models.pkl").open("rb") as f:orig=pickle.load(f)
    totals=defaultdict(Counter);pub=read("transfer_results.json");ncase=0;rs=set();po=0;checked=0
    for p in sorted((D/"transfer_inputs").glob("*.parquet")):
        i=-1;base="random" if "random" in p.name else "first"
        for batch in pq.ParquetFile(p).iter_batches(batch_size=64,columns=["repo_name","context","cropped_code","gold_snippet_index"]):
            for ex in batch.to_pylist():
                i+=1
                if (p.name,i) not in pred:continue
                repo,qh,g,orders=pred[(p.name,i)];n=len(ex["context"]);rowgold=ex["gold_snippet_index"];ncase+=1;rs.add(repo)
                assert repo==ex["repo_name"].casefold() and repo not in train_repos
                assert qh==hashlib.sha256(ex["cropped_code"].encode()).hexdigest() and qh not in train_hash
                for a,ord in orders.items():
                    assert sorted(ord)==list(range(n));po+=1
                    for k in (1,3,5):
                        hit=rowgold in ord[:k];totals[(a,k)]["all"]+=hit;totals[(a,k)][base]+=hit
                if (p.name,i) in spot:
                    F=compute(ex["cropped_code"],[s["snippet"] for s in ex["context"]],120)
                    for a in ("flat","owner","transition","placebo"):
                        score=orig[a].predict_proba(F[:,ARMS[a][1]])[:,1];assert np.argsort(-score,kind="stable").tolist()==orders[a]
                    mixture=gate.predict_proba([summary(F)])[0,1];assert abs(mixture-g)<1e-12
                    posterior={}
                    for typ,model in experts.items():
                        p1=model.predict_proba(F[:,ARMS["transition"][1]])[:,1]
                        odds=p1/(1.-p1);posterior[typ]=odds/odds.sum()
                    for a,w in [("mix",.5),("gate",mixture)]:
                        prob=posterior["first"]*(1-w)+posterior["random"]*w;assert np.argsort(-prob,kind="stable").tolist()==orders[a]
                    checked+=1
    for (a,k),cts in totals.items():
        for base,v in cts.items():assert pub[base]["metrics"][a]["hits"][[1,3,5].index(k)]==v
    save("transfer_verification.json",dict(status="passed",questions=ncase,rankings=po,recomputed_questions=checked,novel_repositories=len(rs),training_and_reference_repo_overlap=0,training_and_reference_full_query_hash_overlap=0))
if __name__=="__main__":main()
