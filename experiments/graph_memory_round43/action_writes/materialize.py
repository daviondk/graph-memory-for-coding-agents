"""Materialize full post-edit lines with exact evidence for potentially partial boundaries."""
def boundaries(old,new,start,visible):
    left=old.split("\n");right=new.split("\n");end=start+len(left)-1
    prefix=suffix=None
    if len(left)==1:
        row=visible.get(start)
        if row is not None and old:
            i=row.find(old)
            if i>=0 and row.find(old,i+1)<0:prefix=row[:i];suffix=row[i+len(old):]
    else:
        a,b=visible.get(start),visible.get(end)
        if a is not None and a.endswith(left[0]):
            prefix=a[:len(a)-len(left[0])]
        if b is not None and b.startswith(left[-1]):
            suffix=b[len(left[-1]):]
    interior={start+i:x for i,x in enumerate(right) if 0<i<len(right)-1}
    out=dict(interior)
    if len(right)==1:
        if prefix is not None and suffix is not None:out[start]=prefix+right[0]+suffix
    else:
        if prefix is not None:out[start]=prefix+right[0]
        if suffix is not None:out[start+len(right)-1]=right[-1]+suffix
    return interior,out

def choose(entries,start,end,budget):
    def priority(record):
        n=record[0]
        return max(start-n,n-end,0),abs(n-start),n
    remaining=budget;out=[]
    for n,d,sz in sorted(entries,key=priority):
        if sz+1<=remaining:
            out.append([n,d,sz]);remaining-=sz+1
    return out

