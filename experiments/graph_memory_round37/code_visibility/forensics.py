"""Look only at gold errors after freezing all policies. Never emit natural source text."""
from project import *
def main():
    old=get(D/"predictions.json.gz");labels=get(D/"observations.json.gz")
    by=defaultdict(list);rows=[]
    for p in old:
        g=dict(labels[p["q"]]["observed"]);seen=dict(p["mem"]["F"])
        for n,s in p["mem"]["T"]:
            if n not in g or g[n]==s:continue
            by[(p["rid"],p["edit"])].append((p,n,s,g[n],n in seen))
    cohort_info,_=cohort();rid_map={rid:h(rid) for rid in cohort_info if h(rid) in {x[0] for x in by}}
    checked=Counter();ref_map=get(P/"files.json")["events"]
    for ref in ref_map:
        tab=pq.ParquetFile(P/ref["file"])
        for bat in tab.iter_batches(columns=["run_id","event_index","event_json"],batch_size=512):
            ids=bat.column("run_id").to_pylist();idxs=bat.column("event_index").to_pylist()
            for j,(rid,i) in enumerate(zip(ids,idxs)):
                if rid not in rid_map:continue
                tag=rid_map[rid],i
                if tag not in by:continue
                b=json.loads(bat.column("event_json")[j].as_py())["raw"]["observation"]
                before=b["old_content"].split("\n");after=b["new_content"].split("\n")
                for p,n,s,g,from_receipt in by[tag]:
                    def same(line,digest):
                        return line is not None and (h(line)==digest or h(line.expandtabs())==digest or h(line.rstrip("\r"))==digest)
                    pred_new=same(after[n-1] if n<=len(after) else None,s)
                    obs_new=same(after[n-1] if n<=len(after) else None,g)
                    origin=n if p["anchor"] is None or n<p["anchor"] else n-p["delta"]
                    pred_old=None if from_receipt else same(before[origin-1] if 1<=origin<=len(before) else None,s)
                    rows.append(dict(q=p["q"],cohort=p["cohort"],window=p["window"],repo=p["repo"],from_receipt=from_receipt,
                       address=n,old_address=origin if not from_receipt else None,pred_matches_new_snapshot=pred_new,observed_matches_new_snapshot=obs_new,
                       pred_matches_old_snapshot=pred_old))
                    checked[(p["cohort"],p["window"],from_receipt,pred_old,pred_new,obs_new)]+=1
    assert len(rows)==sum(map(len,by.values()))
    save(D/"residual-errors.json",rows)
    print(checked)
if __name__=="__main__":main()
