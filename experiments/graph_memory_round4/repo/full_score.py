"""Score sealed full-data rankings, audit the version and report paper-style micro averages."""
import sys
from collections import defaultdict
from data_io import *
from secondary_score import duo
import numpy as np

def project_ids():
    ids=set()
    for p in files("java","train"):
        names=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()
        ids.update(names[i] for i,_ in read("roster.json")[p.stem])
    return ids

def stats(items,with_ci=False):
    n=len(items);proj={r[3] for r in items}
    d={arm:np.array([x[-1][arm][:4] for x in items]).mean(axis=0).tolist() for arm in items[0][-1]}
    out={"count":n,"repos":len(proj),"metrics":d,"source_mean_candidates":np.mean([x[4] for x in items]),"invalid_gold":sum(x[5] for x in items)}
    if with_ci:out["paired"]={other:duo(items,"graph",other) for other in ("owner","jaccard")}
    return out
def main(source):
    orig=source=="archive"
    work=D/"archive_full" if orig else D/"full"
    ref=read("archive_decision_lock.json" if orig else "full_decision_lock.json")
    cols=defaultdict(list)
    for p in (sorted((D/"archive_inputs").glob("*.parquet")) if orig else files("java","test")):
        cols[panel_name(p.stem)].extend(pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist())
    sample={(panel,i):(h,arms["graph"]) for panel,i,k,r,sz,h,e,arms in gz(D/"java.pred.jsonl.gz") if k==3} if not orig else {}
    ids=project_ids(); by=defaultdict(list); samples=Counter();seen=set();projs_in_train=Counter()
    outname=source+".scores.jsonl.gz"
    with gzip.open(D/outname,"wt",encoding="utf8") as o, gzip.open(D/(source+".pred.jsonl.gz"),"wt",encoding="utf8") as p_out:
        for piece in ref["shards"]:
            p=work/piece["file"];assert sha(p)==piece["hash"]
            for panel,j,repo,h,rankings in gz(p):
                assert (panel,j) not in seen;seen.add((panel,j));gold=cols[panel][j];nc=len(rankings["graph"])
                for a,ranking in rankings.items():
                    assert sorted(ranking)==list(range(nc))
                fail=not 0<=gold<nc
                row={}
                for a,v in rankings.items():
                    rank=float("inf") if fail else v.index(gold)+1
                    row[a]=[int(rank==1),int(rank<=3),int(rank<=5),1/rank,0.]
                item=[panel,j,3,repo,nc,fail,row];by[panel].append(item)
                projs_in_train[repo]+=int(repo in ids)
                o.write(json.dumps(item,separators=(",",":"))+"\n")
                p_out.write(json.dumps([panel,j,repo,h,rankings],separators=(",",":"))+"\n")
                if (panel,j) in sample:
                    hh,rv=sample[panel,j];samples["ids"]+=1;samples["same_rank"]+=int(rv==rankings["graph"])
    assert len(seen)==sum(map(len,cols.values()))
    allrows=sum(by.values(),[])
    result={"source":source,"metric_order":["acc@1","acc@3","acc@5","MRR"],"groups":{k:stats(v) for k,v in by.items()},
            "all":stats(allrows,True),"train_project_overlap":sum(v>0 for v in projs_in_train.values()),
            "rows_in_training_projects":sum(projs_in_train.values()),"author_crop_diff_count":sum(s["changed_crop"] for s in ref["shards"]),
            "canonical_overlap":dict(samples),"sha_scores":sha(D/outname),"sha_predictions":sha(D/(source+".pred.jsonl.gz"))}
    for lev in ("easy","hard","cff","cfr"):
        v=[row for p,rows_ in by.items() if lev in p for row in rows_]
        result[lev]=stats(v,True)
    broad=[i for i in allrows if i[3] not in ids]
    if len(broad)!=len(allrows):result["unseen_projects_only"]=stats(broad,True)
    write(source+"_results.json",result)
    for tag in ("easy","hard","all"):print(tag,result[tag]["count"],result[tag]["metrics"],flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "full")
