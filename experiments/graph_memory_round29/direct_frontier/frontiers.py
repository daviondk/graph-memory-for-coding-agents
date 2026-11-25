"""Construct complete half-open exclusion frontiers with float32 score and stable source ties."""
import numpy as np

def pack_keys(score,order):
    score=np.asarray(score,dtype=np.float32)
    bits=np.where(score==0,np.float32(0),score).view(np.uint32)
    sortable=bits^np.where(bits>>np.uint32(31),np.uint32(0xffffffff),np.uint32(0x80000000))
    return (sortable.astype(np.uint64)<<np.uint64(32)) | (np.uint64(0xffffffff)-order.astype(np.uint64))

def record(windows,order,k):
    token,d=divmod(int(order),k);w,i=divmod(token,384);a,b,_,lo,hi=windows[w]
    return (float(a[i]+b[i+d]),int(order),int(lo[i]),int(hi[i+d]))

def grids(n,k,backward=False):
    positions=np.arange(n)[:,None];dist=np.arange(min(k,n))
    if backward:
        offsets=dist[::-1];other=positions-offsets
        return other>=0,np.maximum(other,0)
    other=positions+dist
    return other<n,np.minimum(other,n-1)

def full_sort(ws,k):
    sv=[];ov=[];lv=[];hv=[]
    for w,(a,b,seg,lo,hi) in enumerate(ws):
        if not len(a):continue
        valid,ends=grids(len(a),k)
        i,d=np.where(valid&(seg[:,None]>=0)&(seg[:,None]==seg[ends]))
        sv.append(a[i]+b[i+d]);ov.append(((w*384+i)*k+d).astype(np.int32))
        lv.append(lo[i]);hv.append(hi[i+d])
    if not sv or not any(map(len,sv)):return [],[]
    score,order,lo,hi=map(np.concatenate,(sv,ov,lv,hv))
    byscore=np.lexsort((order,-score));rank=np.empty(len(order),dtype=np.int32);rank[byscore]=np.arange(len(order))
    out=[]
    for endpoints,sgn in ((hi,1),(-lo,-1)):
        ids=np.lexsort((rank,endpoints));x=endpoints[ids]
        first=np.r_[True,x[1:]!=x[:-1]]
        i=ids[first];running=np.minimum.accumulate(rank[i]);changes=np.r_[True,running[1:]<running[:-1]]
        rid=byscore[running[changes]]
        out.append([(int(bound)*sgn,float(score[z]),int(order[z]),int(lo[z]),int(hi[z])) for bound,z in zip(endpoints[i[changes]],rid)])
    return tuple(out)

def earliest_max(values,offset,left,right,k):
    # Each interval is nonempty and stays in one original segment. A smaller logit may tie after float32 addition.
    n=len(values);m=min(k,n).bit_length();tree=np.full((m,n),-np.inf,dtype=np.float32);tree[0]=values
    for z in range(1,m):
        size=1<<z;count=n-size+1;half=size//2
        tree[z,:count]=np.maximum(tree[z-1,:count],tree[z-1,half:half+count])
    lengths=right-left+1
    log=np.frexp(lengths.astype(np.float64))[1].astype(np.int32)-1
    high=np.maximum(tree[log,left],tree[log,right-(1<<log)+1])
    objective=high+offset;pos=left.copy()
    for level in reversed(range(m)):
        jump=1<<level
        legal=pos+jump-1<=right
        # An interval containing only smaller rounded scores can be skipped as a whole.
        skip=legal & ((tree[level,pos]+offset)<objective)
        pos+=skip.astype(pos.dtype)*jump
    return pos,objective

def update(side,index,score,order):
    np.maximum.at(side,index,pack_keys(score,order))

def collapse_matrix(ws,k):
    return reduced(ws,k,"endpoint_matrix")

def streaming(ws,k):
    return reduced(ws,k,"stream")

def dyadic(ws,k):
    return reduced(ws,k,"dyadic")

def reduced(ws,k,method):
    active=[v for v in ws if np.any(v[2]>=0)]
    if not active:return [],[]
    xs=np.unique(np.concatenate([v[4][v[2]>=0] for v in active]));ys=np.unique(np.concatenate([v[3][v[2]>=0] for v in active]))
    pre=np.zeros(len(xs),dtype=np.uint64);suf=np.zeros(len(ys),dtype=np.uint64)
    for w,(a,b,seg,lo,hi) in enumerate(ws):
        ok=seg>=0;ind=np.flatnonzero(ok);n=len(a)
        if not len(ind):continue
        ei=np.searchsorted(xs,hi);si=np.searchsorted(ys,lo)
        if method=="stream":
            valid,ends=grids(n,k);i,d=np.where(valid&ok[:,None]&(seg[:,None]==seg[ends]))
            j=i+d;order=(w*384+i)*k+d;keys=pack_keys(a[i]+b[j],order)
            np.maximum.at(pre,ei[j],keys);np.maximum.at(suf,si[i],keys)
            continue
        runs=seg[np.r_[True,seg[1:]!=seg[:-1]]]; runs=runs[runs>=0]
        if method=="endpoint_matrix" or len(runs)!=len(np.unique(runs)):
            valid,ends=grids(n,k);allowed=valid&(seg[:,None]==seg[ends])
            scores=np.where(allowed,a[:,None]+b[ends],np.float32(-np.inf))
            dist=np.argmax(scores[ind],axis=1);end_pick=ind+dist;forward=scores[ind,dist]
            valid,starts=grids(n,k,True);allowed=valid&(seg[:,None]==seg[starts])
            scores=np.where(allowed,a[starts]+b[:,None],np.float32(-np.inf))
            col=np.argmax(scores[ind],axis=1);start_pick=starts[ind,col];back=scores[ind,col]
        else:
            pos=np.arange(n)
            run_begin=np.maximum.accumulate(np.where(np.r_[True,seg[1:]!=seg[:-1]],pos,0))
            run_end=np.minimum.accumulate(np.where(np.r_[seg[1:]!=seg[:-1],True],pos,n)[::-1])[::-1]
            end_pick,forward=earliest_max(b,a[ind],ind,np.minimum(ind+k-1,run_end[ind]),k)
            start_pick,back=earliest_max(a,b[ind],np.maximum(ind-k+1,run_begin[ind]),ind,k)
        update(pre,ei[ind],back,(w*384+start_pick)*k+ind-start_pick)
        update(suf,si[ind],forward,(w*384+ind)*k+end_pick-ind)
    output=[]
    for coords,values in ((xs,pre),(ys[::-1],suf[::-1])):
        values=np.maximum.accumulate(values);changed=np.r_[True,values[1:]!=values[:-1]]&(values!=0)
        idx=np.flatnonzero(changed);ords=np.uint64(0xffffffff)-(values[idx]&np.uint64(0xffffffff))
        output.append([(int(coords[i]),*record(ws,o,k)) for i,o in zip(idx,ords)])
    return tuple(output)

METHODS={"full_sort":full_sort,"stream":streaming,"endpoint_matrix":collapse_matrix,"dyadic":dyadic}
