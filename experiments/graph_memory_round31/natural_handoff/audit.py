"""Repeat delivery from the real public prompt bytes and account for paths separately from verbatim lines."""
from collections import Counter,defaultdict
from statistics import mean
from hashlib import sha256
from math import isclose
import re
import numpy as np
from source import *
def main():
    rows=get(D/"delivery-metadata.json.gz");pre={r["cp"]:r for r in get(P/"prefix.json.gz")};target={r["q"]:r["target"] for r in get(P/"targets.json.gz")};cases={r["group"]:r for r in get(D/"fixed-outcomes.json.gz")};res=get(D/"results.json")
    groups=defaultdict(dict);rawnote={};rawprompt={};nt=0
    for row in rows:groups[row["group"]][row["view"]]=row
    for path in sorted((P/"data/handoffs").glob("*.parquet")):
        for x in pq.read_table(path,columns=["run_id","rendered_prompt","handoff_view"]).to_pylist():
            if x["handoff_view"] is None:continue
            q=h(x["run_id"]);rawprompt[q]=x["rendered_prompt"];s=rawprompt[q].splitlines()
            st=next((j for j,l in enumerate(s) if l.startswith("=== PREVIOUS AGENT ") and l.endswith(" BEGINS ===")),None)
            en=next((j for j,l in enumerate(s) if l.startswith("=== PREVIOUS AGENT ") and l.endswith(" ENDS ===")),None)
            rawnote[q]="\n".join(s[st+1:en]) if st is not None and en is not None else ""
    for row in rows:assert h(rawprompt[row["q"]])==row["sha"]
    store={};query=defaultdict(list)
    for g,c in cases.items():
        vv=groups[g];rr=vv["repo_only"];t=target[rr["q"]];path,lo,hi=t;asked=[(path,z[0],z[1]) for z in (lo,hi)]
        if rr["cp"] not in store:
            r=pre[rr["cp"]];store[r["cp"]]={(e["path"],ln,s) for e in r["events"] for ln,s in e["lines"]}
        address=store[rr["cp"]];assert all((k in address) for k in asked)==c["available_pair"]
        out={}
        for view,row in vv.items():
            q=row["q"];note=rawnote[q];full=rawprompt[q];lines=note.splitlines();assert len(lines)==0 if view=="repo_only" else len(lines)>0
            found=[False,False];curr=None
            for line in lines:
                if "cat -n" in line and " on /" in line:
                    suffix=line.split(" on /")[-1].strip().rstrip(":");curr=suffix.split("/",1)[1] if suffix.startswith(("testbed/","workspace/")) else None;continue
                space=line.lstrip(" ");left,sep,text=space.partition("\t")
                if not sep or not left.isdigit():curr=None;continue
                triple=(curr,int(left),text)
                for i,k in enumerate(asked):
                    if k==triple and k in address:found[i]=True
            weak=[k in address and k[2] in note for k in asked]
            assert [int(all(found)),mean(found),int(all(weak)),mean(weak)]==c["arms"][view][:4]
            patt=re.escape(path)
            def explicit(z,ln):
                return re.search(patt+r"(?::|#L)"+str(ln)+r"(?!\d)",z) is not None
            out[view]=[int(path in note),int(path in full),int(all(explicit(note,k[1]) for k in asked)),int(c["available_pair"])]
            nt+=1
        query[c["subset"]].append((c["issue"],g,out))
    addr={}
    for subset,seq in query.items():
        addr[subset]={}
        for view in seq[0][2]:
            by=defaultdict(list)
            for issue,g,results in seq:by[issue].append(results[view])
            av=np.mean([np.mean(v,axis=0) for v in by.values()],axis=0).tolist()
            addr[subset][view]=dict(zip(("literal_path_note","literal_path_full_input","two_explicit_path_colon_or_anchor_line","previously_available_pair"),av))
        rows=sorted({i for i,_,_ in seq});matched=[c for c in cases.values() if c["subset"]==subset];bi={i:[c for c in matched if c["issue"]==i] for i in rows}
        n=len(rows);draw=np.random.default_rng(31031).integers(0,n,(10000,n))
        for a,b in (("rrf3","rrf2"),("rrf3","bm25"),("raw_trace","summary_notes")):
            for j,k in enumerate(("pair","fraction")):
                diff=np.array([mean(c["arms"][a][j]-c["arms"][b][j] for c in v) for v in bi.values()]);truth=res["fixed"][subset]["all"]["paired"][a+"__"+b][k]
                assert isclose(diff.mean(),truth["delta"],abs_tol=2e-13) and np.allclose(np.quantile(diff[draw].mean(1),[.025,.975]),truth["ci"],rtol=0,atol=2e-13)
    save(D/"independent-audit.json",dict(bytes_verified_takeover_inputs=len(get(D/"delivery-metadata.json.gz")),fixed_matched_views_verified=nt,per_source_original_inputs=len(store),secondary_posthoc_path_addressing=addr,paired_bootstraps_repeated=18));print(nt,addr["main_takeovers"])
if __name__=="__main__":main()

