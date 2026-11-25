"""Evaluate exact exclusion frontiers and local result reuse against complete forwards."""
from bisect import bisect_right
from collections import defaultdict
import hashlib
from pathlib import Path
import struct
import zlib
from capture import HERE,PRIVATE,PREVIOUS,P,read,save,sha,np

def candidates(data,mode,windows):
    records=[]
    winners=[]
    for w,(idhash,maskhash,size,ns) in enumerate(windows):
        get=lambda k:data[f"{mode}_{w}_{k}"]
        a,b,seg,lo,hi=[get(k) for k in ("a","b","seg","lo","hi")]
        n=len(a);assert a.shape==b.shape==seg.shape==lo.shape==hi.shape
        source=np.arange(n)[:,None];stops=source+np.arange(30)[None,:]
        end=np.minimum(stops,n-1)
        valid=(stops<n)&(seg[:,None]>=0)&(seg[:,None]==seg[end])
        starts,dist=np.where(valid);ends=starts+dist
        scores=a[starts]+b[ends]
        order=w*384*30+starts*30+dist
        if len(scores):
            best=int(np.argmax(scores));candidate=[int(starts[best]),int(dist[best]),float(scores[best])]
        else:candidate=None
        winners.append(candidate)
        records.append((scores,order,lo[starts],hi[ends]))
    if not records:return None,winners
    return [np.concatenate(col) for col in zip(*records)],winners

def result(table,index):
    if index is None:return None
    score,order,lo,hi=table
    return [float(score[index]),int(order[index]),int(lo[index]),int(hi[index])]

def make_index(table):
    score,order,lo,hi=table
    rank_to_id=np.lexsort((order,-score))
    ranks=np.empty(len(score),dtype=np.int32);ranks[rank_to_id]=np.arange(len(score))
    state=[]
    for endpoint in (hi,-lo):
        indices=np.lexsort((ranks,endpoint));points=endpoint[indices]
        first=np.r_[True,points[1:]!=points[:-1]]
        idx=indices[first];current=np.minimum.accumulate(ranks[idx])
        change=np.r_[True,current[1:]<current[:-1]]
        state.append((endpoint[idx[change]].tolist(),rank_to_id[current[change]].tolist()))
    return rank_to_id,state

def search(table,state,low,high):
    candidates=[]
    for (keys,ids),cut in zip(state,(low,-high)):
        index=bisect_right(keys,cut)-1
        if index>=0:candidates.append(ids[index])
    return min(candidates,key=lambda i:(-table[0][i],table[1][i])) if candidates else None

def bytes_state(table,front):
    raw=b"".join(struct.pack("<ifIii",coord,*result(table,idx)) for keys,ids in front for coord,idx in zip(keys,ids))
    return len(raw),len(zlib.compress(raw,6))

def controls(table,ranked,state,cut):
    lo,hi=cut
    allowed=(table[3]<=lo)|(table[2]>=hi)
    valid=ranked[allowed[ranked]]
    brute=next(iter(valid),None)
    idx=search(table,state,lo,hi)
    assert idx==brute
    first_rank=int(np.argmax(allowed[ranked]))+1 if len(valid) else None
    return {"answer":result(table,idx),"rank":first_rank,"allowed":int(allowed.sum())}

def rebuild(base_desc,new_desc,base_best,new_best,new_table):
    cache={};prefix=True;prefix_hits=0;matched=0;logit_hits=0;loss_ns=0
    keys={tuple(w[:2]):val for w,val in zip(base_desc,base_best)}
    ids={w[0] for w in base_desc}
    merged=[]
    for w,row in enumerate(new_desc):
        k=tuple(row[:2])
        if k in keys:
            candidate=keys[k];assert candidate==new_best[w];matched+=1
        else:candidate=new_best[w];loss_ns+=row[3]
        if row[0] in ids:logit_hits+=1
        prefix=bool(prefix and w<len(base_desc) and tuple(base_desc[w][:2])==k)
        prefix_hits+=int(prefix)
        if candidate is not None:
            start,dist,score=candidate;merged.append((score,w*384*30+start*30+dist))
    if new_table is None or not len(new_table[0]):winner=None
    else:
        scored,ord_=new_table[:2];best=int(np.argmax(scored));winner=(float(scored[best]),int(ord_[best]))
    assert (min(merged,key=lambda x:(-x[0],x[1])) if merged else None)==winner
    return {"windows":len(new_desc),"exact_cache":matched,"logit_cache":logit_hits,"prefix_cache":prefix_hits,
            "measured_full_ns":sum(x[3] for x in new_desc),"recompute_subset_ns":loss_ns}

def main():
    seal=read(HERE/"forecast-seal.json")
    assert sha(HERE/"state-forecasts.json.gz")==seal["forecasts"]
    old=read(PREVIOUS/"predictions.json.gz");fixtures=read(HERE/"state-forecasts.json.gz")
    blind=read(P/"blind-input.json.gz");root=PRIVATE/seal["plan"];rows={}
    for q,case in fixtures.items():
        datafile=root/(q+".npz");assert sha(datafile)==case["arrays"]
        with np.load(datafile,allow_pickle=False) as data:
            tables={};wins={};choices={}
            for mode,d in case["states"].items():
                tab,win=candidates(data,mode,d["windows"]);tables[mode]=tab;wins[mode]=win
                choices[mode]=(result(tab,int(np.argmax(tab[0]))) if tab is not None and len(tab[0]) else None)
            for mode,arm in (("base","base"),("append","both")):
                v=choices[mode];actual=old[q]["arms"][arm]
                assert [v[0],v[2],v[3]]==[actual["score"],actual["start"],actual["end"]],q
            table=tables["base"];rated,front=make_index(table)
            base=case["states"]["base"]
            eligible=[x for x in base["parts"] if x[:2]!=case["cut"]]
            random_part=min(eligible or base["parts"],key=lambda x:hashlib.sha256((q+str(x)).encode()).digest())
            width=case["old_answer"][1]-case["old_answer"][0]
            span=min(width,random_part[1]-random_part[0]);room=random_part[1]-random_part[0]-span
            pos=random_part[0]+int.from_bytes(hashlib.sha256(("random/"+q).encode()).digest()[:8],"big")%(room+1)
            scenarios={"winner":case["old_answer"],"record":case["cut"],"random":[pos,pos+span]}
            outputs={name:{"cut":cut,**controls(table,rated,front,cut)} for name,cut in scenarios.items()}
            # Multiple genuine interval endpoints from the visible receipts exercise the lookup.
            for l,r,_ in base["parts"]:
                controls(table,rated,front,(l,r))
            counts=[len(x[0]) for x in front];state_bytes,compressed=bytes_state(table,front)
            logit_bytes=sum(8*w[2] for w in base["windows"])
            aggs={m:rebuild(base["windows"],case["states"][m]["windows"],wins["base"],wins[m],tables[m]) for m in ("append","retract")}
            text=blind["docs"][case["title"]]
            projected=outputs["record"]["answer"];fresh=choices["retract"]
            def textkey(v):return None if v is None else hashlib.sha256(text[v[2]:v[3]].encode()).hexdigest()
            rows[q]={"article":case["title"],"answers":choices,"projections":outputs,"coverage":aggs,"candidates":len(rated),
                     "frontiers":counts,"state_bytes":state_bytes,"zlib_bytes":compressed,"logit_bytes":logit_bytes,
                     "base_windows":len(base["windows"]),"max_payload_bytes":8*len(base["windows"]),
                     "same_source":(projected is None and fresh is None or projected is not None and fresh is not None and projected[2:]==fresh[2:]),
                     "same_surface":textkey(projected)==textkey(fresh)}
    save(HERE/"decisions.json.gz",rows)
    save(HERE/"decision-seal.json",{"forward":sha(HERE/"forecast-seal.json"),"code":sha(Path(__file__)),"decisions":sha(HERE/"decisions.json.gz"),"n":len(rows)})
if __name__=="__main__":main()

