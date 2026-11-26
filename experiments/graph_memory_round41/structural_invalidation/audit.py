"""After forecast binding, independently validate every mapped source block against the trusted snapshots."""
from collections import Counter

from shared import *

METHODS=("file","range","ast","content")


def main():
    pred=read(D/"predictions.json.gz");seal=read(D/"forecast-seal.json")
    assert seal["results"]==sha(D/"predictions.json.gz")
    events,plans,views=inputs();out={}
    for key,row,_,old,new in stream(events):
        P=pred[key];rid=row["run"]
        pool,_=plans[rid][str(row["at"])];reference={n:ev for n,ev,*_ in views[rid][str(row["view"])]}
        before=list(map(h,old.split("\n")));after=list(map(h,new.split("\n")))
        target=row["path"];shape={i:(p,lo,hi,c) for i,p,lo,hi,c,_,_ in pool}
        assert list(row["old"])==P["old"]
        trace={}
        for meth in METHODS:
            candidates=P["maps"][meth];chosen=P["choices"][meth];same=chosen==P["old"]
            counts=Counter(whole_same=int(same),empty=int(not chosen),
                returned_bytes=sum(shape[i][3] for i in chosen),selected_target=sum(shape[i][0]==target for i in chosen),
                old_target=sum(shape[i][0]==target for i in P["old"]))
            for k,(lo,hi) in candidates.items():
                i=int(k);path,low,high,nbytes=shape[i];assert path==target and (hi-lo)==(high-low)
                expect=[reference[x] for x in range(low,high+1)]
                right_before=(1<=low<=high<=len(before) and before[low-1:high]==expect)
                right_after=(1<=lo<=hi<=len(after) and after[lo-1:hi]==expect)
                counts["n_mapped"]+=1;counts["mapped_bytes"]+=nbytes;counts["mapped_lines"]+=len(expect)
                counts["bad_old"]+=int(not right_before);counts["bad_new"]+=int(not right_after)
                if i in chosen:
                    counts["selected_bytes_mapped"]+=nbytes;counts["selected_mapped"]+=1
                    counts["selected_bad_after"]+=int(not right_after)
                    counts["selected_bad_before"]+=int(not right_before)
            assert counts["selected_mapped"]==counts["selected_target"]
            counts["strict"]=int(same and not counts["selected_bad_after"])
            trace[meth]=dict(counts)
        out[key]=dict(issue=P["issue"],held=P["held"],group=P["group"],parsed=P["flags"]["parsed"],
                      old_empty=not P["old"],old_target=bool(trace["range"]["old_target"]),metrics=trace)
    assert len(out)==2696
    save("audit.json.gz",out);save("audit-seal.json",dict(sha=sha(D/"audit.json.gz"),
         forecasts=sha(D/"forecast-seal.json"),program=sha(D/"audit.py"),source=sha(RAW/"files.json")))
    print("Independently audited",len(out),"cases and all mapped target blocks.")


if __name__=="__main__":main()

