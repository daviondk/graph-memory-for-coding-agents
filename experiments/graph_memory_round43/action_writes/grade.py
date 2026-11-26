from collections import Counter
from shared import *

PAIRS=(("boundary","rebase"),("boundary","prior"),("boundary","verbatim"),("boundary","interior"),("rebase","prior"))

def limits(ma,mb,A,B,closed):
    value=int(ma)-int(mb)
    if closed or ma and mb:return [value,value]
    if ma:return [int(not B),1]
    if mb:return [-1,-int(not A)]
    return [-int(bool(B-A)),int(bool(A-B))]


def observations(events):
    import pyarrow.parquet as pq
    wanted=defaultdict(dict)
    for row in events:wanted[row["run"]][row["receipt"]]=row
    memo={};ids=set()
    for ref in read(RAW/"files.json")["events"]:
        path=RAW/ref["file"];assert sha(path)==ref["sha"]
        for batch in pq.ParquetFile(path).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,i) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in memo:memo[run]=h(run)
                rid=memo[run]
                if rid not in wanted or i not in wanted[rid]:continue
                raw=json.loads(batch.column(2)[j].as_py())["raw"]["observation"]
                assert raw["command"]=="str_replace" and not raw["is_error"]
                row=wanted[rid][i];key=h(rid+"/"+str(i));assert key not in ids;ids.add(key)
                yield key,row,raw["new_content"].split("\n")
    assert len(ids)==len(events)


def main():
    pred=read(D/"forecasts.json.gz");f=read(D/"forecast-seal.json");assert sha(D/"forecasts.json.gz")==f["sha"]
    events=signed(G,"selections.json.gz");demand=signed(F,"requests.json.gz");out={}
    for key,row,after in observations(events):
        p=pred[key];w=demand["windows"][key];vv=[demand["by_run"][row["run"]][str(i)] for i in w["reads"]]
        receipt=set(map(tuple,p["receipt"]));need=[{(n,d):size for n,d,size in v} for v in vv]
        lookup={}
        def correct(n,d):
            if n not in lookup:lookup[n]=h(after[n-1]) if 1<=n<=len(after) else None
            return lookup[n]==d
        write={};metrics={};bounds={};pool={}
        for m in METHODS:
            forecasts=p["methods"][m];cells=Counter(forecasts["counts"])
            cells["events_attempted"]=int(bool(forecasts["proposed"]))
            cells["events_new"]=int(cells["new_to_base"]>0)
            for n,d,sz,info in forecasts["proposed"]:
                ok=correct(n,d);cells["wrong_candidate"]+=int(not ok);cells["wrong_informative"]+=int(info and not ok)
            write[m]=dict(cells)
        for cap in BUDGETS:
            z=str(cap);ar={};sets={}
            for m in METHODS:
                pack=p["methods"][m]["packs"][z];owned={(n,d) for n,d,_ in pack};sets[m]=owned
                assert not owned&receipt
                a=Counter(emitted=len(pack),wire_bytes=sum(sz+1 for _,_,sz in pack),bad_emitted=sum(not correct(n,d) for n,d,sz in pack))
                for view in need:
                    required=set(view)-receipt;matches=owned&required
                    a.update(dict(lines=len(matches),bytes=sum(view[q] for q in matches),served_views=int(bool(matches)),
                                  full_with_receipt=int(not(required-matches)),extra_full_views=int(bool(required) and not(required-matches))))
                a["hit"]=int(a["lines"]>0);a["upper"]=int(a["hit"] or (not w["closed"] and bool(owned)))
                ar[m]=dict(a)
            bounds[z]={m+"_minus_"+b:limits(ar[m]["hit"],ar[b]["hit"],sets[m],sets[b],w["closed"]) for m,b in PAIRS}
            metrics[z]=ar
        out[key]=dict(group=p["group"],held=p["held"],issue=p["issue"],repo=p["repo"],closed=w["closed"],views=len(vv),
                      novel_views=sum(bool(set(v)-receipt) for v in need),novel_demand=sum(len(set(v)-receipt) for v in need),
                      rebase_succeeded=p["proper_old_match"],write=write,metrics=metrics,bounds=bounds)
    save("outcomes.json.gz",out);save("grade-seal.json",dict(outcomes=sha(D/"outcomes.json.gz"),forecast=sha(D/"forecast-seal.json"),
             future=sha(F/"requests.json.gz"),raw=sha(RAW/"files.json"),program=sha(D/"grade.py")))
    print("Independently audited post-revision and future-demand effects for",len(out),"confirmed writes.")
if __name__=="__main__":main()

