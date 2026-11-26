"""Derive only whole-line byte-preserving address maps from a disclosed literal replacement."""
import hashlib
from difflib import SequenceMatcher

MAX_CENTRAL_PRODUCT=65536


def tokens(s):
    fields=s.split("\n")
    # The unobserved file prefix and suffix are shared between versions, yet never compared to ordinary lines.
    return [hashlib.sha256(bytes((int(i==0),int(i==len(fields)-1)))+field.encode()).hexdigest()
            for i,field in enumerate(fields)]


def match(old,new):
    n,m=len(old),len(new)
    left=0
    while left<min(n,m) and old[left]==new[left]:
        left+=1
    end_old,end_new=n,m
    while end_old>left and end_new>left and old[end_old-1]==new[end_new-1]:
        end_old-=1;end_new-=1
    edges={j:j for j in range(left)}
    edges.update({j:end_new+j-end_old for j in range(end_old,n)})
    total=dict(edges);product=(end_old-left)*(end_new-left);bounded=product>MAX_CENTRAL_PRODUCT
    if not bounded and product:
        matcher=SequenceMatcher(None,old[left:end_old],new[left:end_new],autojunk=False)
        for pos0,pos1,count in matcher.get_matching_blocks():
            for off in range(count):total[left+pos0+off]=left+pos1+off
    values=[total[k] for k in sorted(total)]
    assert values==sorted(set(values)) and all(old[k]==new[dest] for k,dest in total.items())
    return edges,total,dict(left=left,right=n-end_old,central=len(total)-len(edges),bounded=bounded,product=product)


def project(low,high,start,end,delta,inner):
    # Coordinates are inclusive; inner indices are zero based and scoped to the operation literals.
    dest=[]
    for q in range(low,high+1):
        if q<start:dest.append(q)
        elif q>end:dest.append(q+delta)
        elif q-start in inner:dest.append(start+inner[q-start])
        else:return None
    if not dest or any(y!=x+1 for x,y in zip(dest,dest[1:])):return None
    return [dest[0],dest[-1]]

