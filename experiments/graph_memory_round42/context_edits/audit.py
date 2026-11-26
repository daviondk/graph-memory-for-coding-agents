"""Score complete selected lists, then compare literal emitted rows with source versions."""
from collections import Counter
from local import *
from shared import stream

def main():
    seal=read(D/"forecast-seal.json");pred=read(D/"predictions.json.gz")
    assert sha(D/"predictions.json.gz")==seal["predictions"]
    events=signed(G,"selections.json.gz");plans=signed(G,"guarded-plans.json.gz")
    views=signed(V,"visible.json.gz");base=signed(S,"audit.json.gz")
    result={}
    for key,row,_,old,new in stream(events):
        before=old.split("\n");after=new.split("\n");p=pred[key]
        address={n:t for n,t,*_ in views[row["run"]][str(row["view"])]}
        inc,_=plans[row["run"]][str(row["at"])]
        shapes={i:(path,lo,hi,cost) for i,path,lo,hi,cost,util,v in inc}
        r={"issue":p["issue"],"repo":p["repo"],"held":p["held"],"group":p["group"],
           "old_target":p["target_selected"],"metrics":dict(base[key]["metrics"])}
        for m in ("edges","local"):
            positions=p["positions"][m];seq=p["choices"][m];same=seq==p["old"]
            c=Counter(whole_same=int(same),empty=int(not seq),returned_bytes=sum(shapes[i][3] for i in seq),
                selected_target=sum(shapes[i][0]==row["path"] for i in seq),
                old_target=sum(shapes[i][0]==row["path"] for i in p["old"]))
            for k,(u,v) in positions.items():
                i=int(k);path,lo,hi,nbytes=shapes[i];assert path==row["path"] and hi-lo==v-u
                wanted=[address[n] for n in range(lo,hi+1)]
                ok=1<=u<=v<=len(after) and wanted==list(map(h,after[u-1:v]))
                prior=1<=lo<=hi<=len(before) and wanted==list(map(h,before[lo-1:hi]))
                c["n_mapped"]+=1;c["mapped_bytes"]+=nbytes;c["mapped_lines"]+=len(wanted)
                c["bad_old"]+=int(not prior);c["bad_new"]+=int(not ok)
                if i in seq:
                    c["selected_mapped"]+=1;c["selected_bytes_mapped"]+=nbytes;c["selected_bad_after"]+=int(not ok)
                    c["selected_bad_before"]+=int(not prior)
            assert c["selected_mapped"]==c["selected_target"]
            c["strict"]=int(same and not c["selected_bad_after"])
            r["metrics"][m]=dict(c)
        result[key]=r
    save("audit.json.gz",result)
    save("audit-seal.json",dict(audit=sha(D/"audit.json.gz"),source=sha(RAW/"files.json"),
         predicted=sha(D/"forecast-seal.json"),baselines=sha(S/"audit.json.gz"),program=sha(D/"audit.py")))
    print("Audited",len(result),"states and all transferred incidences.")
if __name__=="__main__":main()

