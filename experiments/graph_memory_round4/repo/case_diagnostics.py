"""Draw two illustrative repeat-call disagreements deterministically, then report graph witnesses."""
from experiment import *
from memory import wt,pp,cos
from data_io import *
from collections import defaultdict

def main():
    pred={}
    for panel,j,k,pr,c,h,e,arms in gz(D/"java.pred.jsonl.gz"):
        if k==3 and "_cfr_" in panel:pred[panel,j]=[arms["owner"][0],arms["graph"][0]]
    allgold=defaultdict(list)
    for p in files("java","test"):
        allgold[panel_name(p.stem)].extend(pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist())
    target={}
    for sign in ("rescue","loss"):
        candidates=[(p,j) for (p,j),(a,b) in pred.items() if a!=b and (allgold[p][j]==b if sign=="rescue" else allgold[p][j]==a)]
        target[min(candidates,key=lambda k:hashstr(f"r4-illustration|{k[0]}|{k[1]}"))]=sign
    out={};pos=defaultdict(int)
    for p in files("java","test"):
        panel=panel_name(p.stem)
        if not any(k[0]==panel for k in target):continue
        for j,x in enumerate(rows(p,["repo_name","code","context"])):
            key=(panel,pos[panel]+j)
            if key not in target:continue
            a,b=pred[key];q="\n".join(x["code"].splitlines()[-3:]);qw=pp(q);cs,edges,outgoing,df=encode(x["context"])
            def describe(t):
                evid=[(round(cos(qw,ev)*amb,3),src,sorted(qw&ev)) for src,ev,amb in edges[t]]
                best=max(evid,default=(0,-1,[]));s=best[1]
                return {"candidate":t,"declares":cs[t]["root"],"incoming_edges":len(edges[t]),"incoming_sources":len({ev[0] for ev in edges[t]}),"outdegree":len(outgoing[t]),"strongest_trace_source":cs[s]["root"] if s>=0 else None,"strongest_trace_overlap":best[2][:6],"strongest_trace_similarity":best[0]}
            out[target[key]]={"panel":panel,"id":key[1],"repo":x["repo_name"],"pool":len(cs),"gold":allgold[panel][key[1]],"query_terms":sorted(qw)[:15],"owner":describe(a),"graph":describe(b)}
        pos[panel]+=pq.ParquetFile(p).metadata.num_rows
    assert len(out)==2;write("case_diagnostics.json",out)
if __name__=="__main__":main()
