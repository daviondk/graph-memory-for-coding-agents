"""Decision function requires only visible material and field lengths; no I/O or labels."""
from collections import Counter,defaultdict
from fractions import Fraction
import math,sys
from time import perf_counter_ns
from io24 import R
sys.path.append(str(R/"marginal_open"))
from novelty import make_windows,union_intervals,WORDS
LAMBDAS=(25,50,75)
def relevance(query,wins):
    words=set(WORDS.findall(query.casefold()))
    docs=[Counter(WORDS.findall(w.text.casefold())) for w in wins]
    avg=sum(sum(d.values()) for d in docs)/len(docs) if docs else 0
    avg=avg or 1
    idf={w:math.log1p((len(docs)-df+.5)/(df+.5)) for w in sorted(words) if (df:=sum(w in d for d in docs))}
    scores=[]
    for d in docs:
        norm=1.2*(.25+.75*sum(d.values())/avg)
        scores.append(sum(idf[w]*d[w]*2.2/(d[w]+norm) for w in sorted(words&d.keys())))
    order=sorted(range(len(wins)),key=lambda j:(-scores[j],j))
    top=scores[order[0]] if order else 0.
    return order,([s/top for s in scores] if top else [0.]*len(scores))

def geometry(wins,fragments,field_lengths,cost):
    shown=defaultdict(list)
    for e,l,s in fragments:shown[e].append((l,l+len(s)))
    union={e:union_intervals(v) for e,v in shown.items()};geo=[]
    for j,v in enumerate(wins):
        e,l=v.field,v.start
        budget=max(0,256-cost[j])
        right=min(field_lengths[e],l+(budget*(v.end-l)//v.tokens if v.tokens else budget))
        width=right-l
        def overlap(a,b):return max(0,min(right,b)-max(l,a))
        best=max((overlap(a,b) for a,b in shown[e]),default=0)
        all_=sum(overlap(a,b) for a,b in union[e])
        assert 0<=best<=all_<=width
        geo.append((width,best,all_))
    return geo

def choose_mmr(order,rel,geo,lam,coord,gated=False):
    # Iteration in lexical order gives the preregistered tie order.
    best=None;score=None
    for j in order:
        w,m,u=geo[j]
        if gated and w<=u:continue
        ov=(m if coord=="max" else u)/w if w else 1.
        candidate=lam*rel[j]-(100-lam)*ov
        if score is None or candidate>score:best=j;score=candidate
    return best
def first_positive(order,geo):return next((j for j in order if geo[j][0]>geo[j][2]),None)

def besl(query,fragments,lengths,tok):
    start=perf_counter_ns()
    wins=make_windows(fragments,tok);order,rel=relevance(query,wins)
    stop=perf_counter_ns()
    headers=[len(tok.encode(f"[{v.field}:{v.start}] ",add_special_tokens=False).ids) for v in wins]
    geo=geometry(wins,fragments,lengths,headers);gstop=perf_counter_ns()
    arms={"bm25":order[0] if order else None,"first_positive":first_positive(order,geo)}
    by_j={j:i for i,j in enumerate(order)}
    eligible=[j for j in order if geo[j][0]>geo[j][2]]
    arms["rank_novelty"]=max(eligible,key=lambda j:Fraction(geo[j][0]-geo[j][2],geo[j][0]*(1+by_j[j]))) if eligible else None
    for coord in ("max","union"):
        for quant in LAMBDAS:arms[f"{coord}_{quant}"]=choose_mmr(order,rel,geo,quant,coord)
        arms[f"{coord}_50_gated"]=choose_mmr(order,rel,geo,50,coord,True)
    # Measure repeated selection on the same precomputed candidate geometry, excluding tokenization.
    methods=[("first_positive",lambda:first_positive(order,geo)),("max_50",lambda:choose_mmr(order,rel,geo,50,"max")),("union_50",lambda:choose_mmr(order,rel,geo,50,"union"))]
    times=defaultdict(list)
    rotation=sum(query.encode())%3
    for turn in range(5):
        for z in range(3):
            name,op=methods[(z+turn+rotation)%3];t0=perf_counter_ns();j=op();elapsed=perf_counter_ns()-t0
            assert j==arms[name];times[name].append(elapsed)
    result={k:None if j is None else [j,wins[j].field,wins[j].start] for k,j in arms.items()}
    return result,{"n":len(wins),"different_penalties":sum(m!=u for w,m,u in geo),"ranking_ns":stop-start,"geometry_headers_ns":gstop-stop,"numeric_ns":{k:sorted(v)[2] for k,v in times.items()}}
def selftest():
    from novelty import Window
    fr=[(0,0,"abc"),(0,5,"def")];g=geometry([Window(0,0,3,"abc",3)],fr,{0:8},[248])
    assert g==[(8,3,6)]
    geo=[(8,3,6),(8,4,4)];assert choose_mmr([0,1],[1.,1.],geo,50,"max")==0 and choose_mmr([0,1],[1.,1.],geo,50,"union")==1
    assert choose_mmr([1,0],[0.,0.],[(0,0,0),(0,0,0)],50,"max")==1 and first_positive([1,0],[(0,0,0),(0,0,0)]) is None
if __name__=="__main__":selftest()
