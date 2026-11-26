"""Verify degree shuffling by physically relabeling both ends of all projected edges."""
from collections import Counter
import hashlib
import numpy as np
from core42 import D,R41,read,save,sha
import features42 as f


def main():
    panel=set(read(R41/"registration.json")["terminal_panel"])
    sdk=f.api.pilot
    tok=sdk.offsets(sdk.Tokenizer.from_file(str(sdk.CACHE/"tokenizer.json")))
    def chunk(s):return sdk.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    counts=Counter()
    for sh in range(8):
        src=f.api.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(src)==read(R41/f"forecast-{sh}-seal.json")["source"]
        for _,raw in sdk.stream(src):
            t=raw["session_id"]
            if t not in panel:continue
            tr=f.native.adapt_isetrace_record(f.native.parse_isetrace_record(raw),source_revision=sdk.RAW[1])
            at,_=f.native.midstep(tr)
            graph=f.native.prefix_graph(tr,at,chunk)
            names,_,meta,edge,sham=f.auxiliary(graph,tr,at,t)
            ids,g=f.packed.geometry({"g":graph})
            assert list(ids)==names
            inv=np.arange(len(names))
            for role in (0,1):
                order=sorted(np.flatnonzero(meta[:,0]==role),key=lambda i: hashlib.sha256(
                    ("ablation42|"+t+"|"+names[i]).encode()).digest())
                for j,target in enumerate(order):
                    inv[order[(j-max(1,len(order)//2))%len(order)]]=target
            members={i:np.flatnonzero(g.membership==i).tolist() for i in set(g.membership)}
            edges=[(int(a),int(b),0) for a,b in g.adjacent]
            for a,b,k in g.links:
                edges.extend((x,y,int(k)) for x in members[a] for y in members[b])
            actual=np.zeros((len(names),8),int);placebo=actual.copy()
            assert len(set(edges))==len(edges)
            for x,y,k in edges:
                actual[x,2*k]+=1;actual[y,2*k+1]+=1
                placebo[inv[x],2*k]+=1;placebo[inv[y],2*k+1]+=1
            assert np.array_equal(np.log1p(actual),edge[:,:8])
            assert np.array_equal(np.log1p(placebo),sham[:,:8])
            counts.update(graphs=1,nodes=len(names),directed_edges=len(edges))
    assert counts["graphs"]==48
    save(D/"permutation-audit.json",dict(counts=counts,code=sha(D/"permutation42.py")))
    print(counts)


if __name__=="__main__":main()
