"""Characterize all admissible double-margin variations via alternating directed cycles."""
from experiment import D,load,put,np,sha
from collections import deque,Counter,defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
def alternative(arcs,selected,n):
    # Sources and sinks occupy separate copies of the vertex space.
    if not arcs:return None
    selected=set(selected);rows=[];cols=[];ids={}
    for j,(a,b) in enumerate(arcs):
        v,w=(b+n,a) if j in selected else (a,b+n);rows.append(v);cols.append(w);ids[v,w]=j
    g=csr_matrix((np.ones(len(rows),np.int8),(rows,cols)),shape=(2*n,2*n))
    count,labels=connected_components(g,directed=True,connection="strong")
    found=np.flatnonzero(np.bincount(labels)>1)
    if not len(found):return None
    comp=int(found[0]);i=next(j for j,(v,w) in enumerate(zip(rows,cols)) if labels[v]==labels[w]==comp);start,end=rows[i],cols[i];prev={end:None};q=deque([end])
    while start not in prev:
        a=q.popleft()
        for v in g.indices[g.indptr[a]:g.indptr[a+1]]:
            if labels[v]==comp and v not in prev:prev[v]=a;q.append(v)
    flip=[i];at=start
    while at!=end:
        before=prev[at];flip.append(ids[before,at]);at=before
    new=selected^set(flip)
    def marg(S):return Counter(arcs[i][0] for i in S),Counter(arcs[i][1] for i in S)
    assert new!=selected and marg(new)==marg(selected) and len(new)==len(selected)
    return flip
def main():
    accepted={};total=0;ex={}
    for sh in range(8):
        for t,r in load(D/f"edges-{sh}.json.gz").items():
            res=alternative(r["extra_edges"],r["H"],r["nodes"]);total+=1
            if res is not None:accepted[t]=res
    for r in range(2,7):
        # A bipartite case with a unique alternating cycle of length 2r.
        arcs=[(i,(i+k)%r) for i in range(r) for k in (0,1)]
        a=alternative(arcs,range(0,len(arcs),2),r);assert len(a)==2*r
        # Removing any one edge from that cycle leaves an acyclic support.
        assert alternative(arcs[:-1],range(0,len(arcs)-1,2),r) is None;ex[str(r)]=len(a)
    p=D/"margin-identifiability.json";put(p,dict(trajectories=total,admissible_alternative_double_degree=len(accepted),certificates=accepted,synthetic_cycle_lengths=ex,code=sha(D/"margins.py")))
    print(total,len(accepted),ex)
if __name__=="__main__":main()