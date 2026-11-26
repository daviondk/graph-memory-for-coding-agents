"""Compute the same paired timing statistics for first read from the on-disk store."""
from summarize import *
from collections import defaultdict
def main():
    raw=get(D/"file-times.json.gz"); groups=defaultdict(list); by=defaultdict(list);arms=("dense","cost","full_rgcn","wo_chunk_adjacency")
    for t,q,rep,pos,a,ns in raw:groups[q,a].append(ns/1e6);by[t].append(q)
    qs=sorted({q for _,q,*_ in raw});assert len(raw)==288 and len(qs)==24 and all(len(v)==3 for v in groups.values())
    mat=np.array([[np.median(groups[q,a]) for a in arms] for q in qs]); ordered=sorted(by);n=len(ordered)
    gids=[sorted({qs.index(q) for q in by[t]}) for t in ordered];sizes=np.array([len(x) for x in gids]);sums=np.stack([mat[x].sum(0) for x in gids])
    rng=np.random.default_rng(13);vals=[]
    for _ in range(100):
        ix=rng.integers(n,size=(100,n));vals.extend(sums[ix].sum(1)/sizes[ix].sum(1)[:,None])
    vals=np.array(vals);mean=mat.mean(0);pairs={}
    for i,j in ((2,1),(3,1),(1,0)):
        pairs[arms[i]+" over "+arms[j]]={"ratio":float(mean[i]/mean[j]),"ratio_ci95":np.quantile(vals[:,i]/vals[:,j],[.025,.975]).tolist(),"delta_ms":float(mean[i]-mean[j]),"delta_ci95_ms":np.quantile(vals[:,i]-vals[:,j],[.025,.975]).tolist()}
    res={"histories":n,"per_query_ms":{a:stats(mat[:,i]) for i,a in enumerate(arms)},"pooled_ms":{a:stats([ns for (q,m),v in groups.items() if m==a for ns in v]) for a in arms},"paired":pairs,"raw":sha(D/"file-times.json.gz")}
    (D/"file-summary.json").write_text(json.dumps(res,sort_keys=True,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":main()
