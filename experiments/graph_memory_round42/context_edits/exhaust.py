"""Independent full-string oracle for toy literals and physical block ranges."""
from itertools import product
from mechanism import tokens,match,project,MAX_CENTRAL_PRODUCT
from local import D,save,sha


def sweep():
    alphabet=("a","b","\n")
    literals=["".join(c) for k in range(1,4) for c in product(alphabet,repeat=k)]
    new_literals=[""]+literals
    counts={"edits":0,"blocks":0,"usable":0,"partial":0,"wrong":0,"edge_usable":0}
    for old in literals:
        for new in new_literals:
            e,m,_=match(tokens(old),tokens(new))
            for pre in ("","p","p\np"):
                for post in ("","s","s\ns"):
                    x=(pre+old+post).split("\n");y=(pre+new+post).split("\n")
                    line=pre.count("\n")+1;end=line+old.count("\n")
                    delta=new.count("\n")-old.count("\n");counts["edits"]+=1
                    for low in range(1,len(x)+1):
                        for hi in range(low,len(x)+1):
                            counts["blocks"]+=1
                            for mapping,name in ((e,"edge_usable"),(m,"usable")):
                                value=project(low,hi,line,end,delta,mapping)
                                if value:
                                    a,b=value;counts[name]+=1
                                    counts["wrong"]+=int(not(1<=a<=b<=len(y) and x[low-1:hi]==y[a-1:b]))
                            if any(q in m for q in range(max(0,low-line),min(hi-line+1,end-line+1))):counts["partial"]+=1
    # Central disjoint 257 by 257 entries exceed the cap; strict mode falls back to the proven edges.
    a,b,z=match(tokens("\n".join("o"+str(i) for i in range(257))),tokens("\n".join("n"+str(i) for i in range(257))))
    assert z["product"]>MAX_CENTRAL_PRODUCT and z["bounded"] and a==b=={}
    assert not counts["wrong"] and counts["usable"]>=counts["edge_usable"]
    return counts


if __name__=="__main__":
    counts=sweep();save("exhaustive.json",dict(counts=counts,threshold=MAX_CENTRAL_PRODUCT,program=sha(D/"exhaust.py")))
    print(counts)

