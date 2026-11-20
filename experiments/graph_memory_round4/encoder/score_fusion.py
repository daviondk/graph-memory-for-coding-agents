from collections import defaultdict
import numpy as np
from common_run import D,hashfile,load,now,readgz,save,writegz

assert hashfile(D/"fusion.pred.jsonl.gz")==load(D/"fusion_decision_lock.json")["pred_sha"]
scores={(r["panel"],r["idx"],r["keep"]):r for r in readgz(D/"scores.jsonl.gz")}
items=defaultdict(list)
detail = []
for panel,i,k,order in readgz(D/"fusion.pred.jsonl.gz"):
    row = scores[panel,i,k]
    rank = order.index(row["gold"])+1
    detail.append([panel,i,k,rank])
    items[k].append((row["project"],rank,row["ranks"]["graph"],row["ranks"]["unix"]))
def describe(rows):
    project,labels = np.unique([r[0] for r in rows],return_inverse=True)
    n=np.bincount(labels)
    draws=np.random.default_rng(20261118).integers(len(n),size=(5000,len(n)))
    f,g,u=np.array([r[1:] for r in rows]).T
    def contrast(other,rr=False,k=1):
        diff=1/f-1/other if rr else (f<=k).astype(int)-(other<=k).astype(int)
        sums=np.bincount(labels,weights=diff)
        boot=sums[draws].sum(axis=1)/n[draws].sum(axis=1)
        return {"delta":float(np.mean(diff)),"lo":float(np.quantile(boot,.025)),"hi":float(np.quantile(boot,.975)),"w":int((diff>0).sum()),"l":int((diff<0).sum())}
    return dict(n=len(rows),at1=int((f==1).sum()),at3=int((f<=3).sum()),at5=int((f<=5).sum()),mrr=float((1/f).mean()),graph_top1=contrast(g),unix_top1=contrast(u),graph_top3=contrast(g,k=3),graph_top5=contrast(g,k=5),unix_top3=contrast(u,k=3),unix_top5=contrast(u,k=5),graph_mrr=contrast(g,True),unix_mrr=contrast(u,True),union=int(((g==1)|(u==1)).sum()),both=int(((g==1)&(u==1)).sum()),only_graph=int(((g==1)&(u>1)).sum()),only_unix=int(((g>1)&(u==1)).sum()),new_hits=int(((f==1)&(g>1)&(u>1)).sum()))
writegz(D/"fusion.scores.jsonl.gz",detail)
out={str(k):describe(v) for k,v in items.items()}
save("fusion_results.json",out)
print(out)

