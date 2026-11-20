"""Zero-label diffusion on observed candidate reference graphs; run after freezing the roster, then score."""
from full_java import *
from collections import defaultdict
from secondary_score import duo
from data_io import gz
import sys

def ppr(lex,edges,shift):
    n=len(lex);q=np.array(lex,dtype=float);q=q/q.sum() if q.sum() else np.repeat(1./n,n)
    a=np.zeros((n,n))
    for dst,events in enumerate(edges):
        for src,text,w in events:a[src,(dst+shift)%n]+=w
    totals=a.sum(axis=1);ok=totals>0;a[ok]/=totals[ok,None];a[~ok]=q
    pos=q.copy()
    for _ in range(120):
        nxt=.15*q+.85*pos@a
        if np.linalg.norm(nxt-pos,ord=1)<1.e-11:break
        pos=nxt
    return np.argsort(-nxt,kind="stable").tolist()
def main():
    canonical=defaultdict(set);strict=defaultdict(set)
    for label,rs,path_ in [("canonical",canonical,D/"java.pred.jsonl.gz"),("strict",strict,D/"strict_java.pred.jsonl.gz")]:
        for panel,j,k,*_ in gz(path_):
            if k==3:rs[panel].add(j)
    apaths=sorted((D/"archive_inputs").glob("*.parquet"))
    arch={panel_name(p.stem):set(sorted(range(pq.ParquetFile(p).metadata.num_rows),key=lambda j:hashstr(f"r4-ppr-archive|{panel_name(p.stem)}|{j}"))[:300]) for p in apaths}
    write("ppr_method_lock.json",{"sha256":{n:sha(D/n) for n in ("PPR_PROTOCOL_RU.md","zero_ppr.py","memory.py","repo_author_similarity.py","repo_author_utils.py")},"archive":{k:sorted(v) for k,v in arch.items()},"counts":[sum(map(len,r.values())) for r in (canonical,strict,arch)]})
    crop=author_function("repo_author_utils.py","crop_code_lines");jacc=author_function("repo_author_similarity.py","jaccard_similarity");tok=Adapter()
    dest=D/"ppr.pred.jsonl.gz"
    with gzip.open(dest,"wt",encoding="utf8") as out:
        for name,rs,paths in [("canonical",canonical,files("java","test")),("strict",strict,files("java","test")),("archive",arch,apaths)]:
            offsets=defaultdict(int)
            for p in paths:
                panel=panel_name(p.stem)
                for rel,r in enumerate(rows(p,["repo_name","code","context"])):
                    j=offsets[panel]+rel
                    if j not in rs[panel]:continue
                    q=crop(r["code"],3) if name=="archive" else "\n".join(r["code"].splitlines()[-3:]);docs=r["context"];edges=encode(docs)[1]
                    sim=[jacc(q,dd,tok) for dd in docs];n=len(docs)
                    shift=1+int(hashstr(q)[:8],16)%max(1,n-1)
                    rank={"jaccard":sorted(range(n),key=lambda j:sim[j],reverse=True),"ppr":ppr(sim,edges,0),"permuted":ppr(sim,edges,shift)}
                    out.write(json.dumps([name,panel,j,r["repo_name"],n,rank],separators=(",",":"))+"\n")
                offsets[panel]+=pq.ParquetFile(p).metadata.num_rows
    write("ppr_decision_lock.json",{"sha256":sha(dest),"utc":datetime.now(timezone.utc).isoformat()})
def score():
    gold={}
    for name,paths in [("archive",sorted((D/"archive_inputs").glob("*.parquet"))),("hf",files("java","test"))]:
        gold[name]=defaultdict(list)
        for p in paths:gold[name][panel_name(p.stem)].extend(pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist())
    assert sha(D/"ppr.pred.jsonl.gz")==read("ppr_decision_lock.json")["sha256"];items=defaultdict(list)
    for name,panel,j,repo,n,rank in gz(D/"ppr.pred.jsonl.gz"):
        g=gold["archive" if name=="archive" else "hf"][panel][j];ranks={a:v.index(g)+1 if g in v else float("inf") for a,v in rank.items()}
        sc={a:[int(pos==1),int(pos<=3),int(pos<=5),1/pos,0] for a,pos in ranks.items()};items[name].append([panel,j,3,repo,sc])
    out={}
    for k,vs in items.items():
        out[k]={"rows":len(vs),"projects":len(set(x[3] for x in vs)),"averages":{a:np.mean([x[-1][a][:4] for x in vs],axis=0).tolist() for a in ("ppr","jaccard","permuted")},"paired":{a:duo(vs,"ppr",a) for a in ("jaccard","permuted")}}
    write("ppr_results.json",out)
if __name__=="__main__":main();score()
