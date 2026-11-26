"""Two independent checks of bounded-failure queries, using only the Python standard library."""
from itertools import combinations,permutations
from pathlib import Path
from statistics import mean
from collections import Counter
import gzip,json,hashlib
D=Path(__file__).resolve().parent;S=D.parents[1]/"graph_memory_round31"
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def states(ids,f):return [frozenset(r) for k in range(f+1) for r in combinations(ids,k)]
def query(edges,ban,heads=None):
    return next((j for j,e in enumerate(edges) if e.isdisjoint(ban) and (heads is None or not e.isdisjoint(heads))),None)
def flat():
    file=S/"support_pairs/rankings.json.gz";data=read(file)
    stats=Counter()
    for q,x in data.items():
        pairs=[frozenset(p) for p in x["pairs"]["joint"]];n=len(x['order']);tree={};winners=set()
        def grow(b):
            if b in tree:return
            j=query(pairs,b);tree[b]=j
            if j is not None:
                winners.add(j)
                if len(b)<2:
                    for k in pairs[j]:grow(b|{k})
        grow(frozenset());m=sorted(winners);enum=set()
        assert len(m)<=6
        for ban in states(range(n),2):
            j=query(pairs,ban);node=frozenset();steps=0
            while True:
                item=tree[node];steps+=1
                if item is None:break
                intersect=pairs[item]&ban
                if not intersect:break
                node=node|{min(intersect)}
            probes=0;flatwinner=None
            for p in m:
                probes+=1
                if pairs[p].isdisjoint(ban):flatwinner=p;break
            assert flatwinner==j==item
            if j is not None:enum.add(j)
            if len(ban)==2:
                stats.update(exact_two=1,nodes_two=steps,flat_two=probes)
        assert set(m)==enum
        stats.update(queries=1,nodes=len(tree),stored=len(m));stats["max_stored"]=max(stats["max_stored"],len(m))
    return {"counts":stats,"mean_node_probes":stats["nodes_two"]/stats["exact_two"],"mean_flat_probes":stats["flat_two"]/stats["exact_two"],"source":sha(file)}
def gated(edges,ids,budget,width,cure=False):
    saved=set();visited=set()
    def go(b):
        if b in visited:return
        visited.add(b);heads=[d for d in ids if d not in b][:width];j=query(edges,b,heads)
        if j is not None:saved.add(j)
        if len(b)<budget:
            for v in (edges[j] if j is not None else heads if cure else []):go(b|{v})
    go(frozenset());return saved
def local_prefix(edges,ids,f,b):
    saved=set()
    for u in ids[:b+f]:saved.update([i for i,e in enumerate(edges) if u in e][:f+1])
    return sorted(saved)
def dynamic():
    ids=tuple(range(4));options=[frozenset(p) for p in combinations(ids,2)];t=Counter();illustration=None
    bans=states(ids,2)
    for size in range(7):
        for edges in permutations(options,size):
            for width in (1,2):
                index=local_prefix(edges,ids,2,width);sub=[edges[i] for i in index];full=set()
                for b in bans:
                    heads=[i for i in ids if i not in b][:width];j=query(edges,b,heads)
                    if j is not None:full.add(j)
                    got=query(sub,b,heads);assert (None if got is None else index[got])==j
                    t['states']+=1
                minimal=gated(edges,ids,2,width);repaired=gated(edges,ids,2,width,True)
                assert full==repaired
                if full!=minimal:
                    assert size<6;t['incomplete_original']+=1
                    if illustration is None:illustration=dict(edges=[sorted(e) for e in edges],width=width,missing=sorted(full-minimal))
                t['rankings_by_width']+=1
    native=S/"hotpot_native";seal=read(native/"ranking-seal.json");cases={};ns=0
    for q,h in seal["forecasts"].items():
        file=native/"forecasts"/(q+".json");assert sha(file)==h.lower();row=read(file)["full"]
        edges=[frozenset(z[:2]) for z in row["pairs"]];ids=row["doc_order"];subset=local_prefix(edges,ids,2,2);minimal=gated(edges,ids,2,2);sub=[edges[i] for i in subset]
        for b in states(ids,2):
            heads=[i for i in ids if i not in b][:2];j=query(edges,b,heads);pos=query(sub,b,heads);assert j==subset[pos];ns+=1
        cases[q]=dict(prefix=len(subset),minimal=len(minimal),full=len(edges))
    return {"sparse":t,"example":illustration,"native":cases,"native_states":ns,"prefix_mean":mean(v['prefix'] for v in cases.values()),"minimal_mean":mean(v['minimal'] for v in cases.values())}
if __name__=="__main__":
    out={"static":flat(),"dynamic":dynamic()};(D/"checks.json").write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf8');print(json.dumps(out))