"""Post-forecast comparison to historical native validation metrics and both packet orders."""
from native_cpu import *
def main():
    assert sha(D/"packets.json.gz")==load(D/"forecast-seal.json")["forecasts"]
    keys=load(W/"graph_memory_round34/interval_witness/dev-geometry.json")["source"]["candidate_sources"]
    by={}
    for filename,v in keys.items():
        path=Path(filename);assert sha(path)==v
        for row in load(path):by[row["q"]]={r["node_id"]:i for i,r in enumerate(row["rr"])}
    positives={}
    for t,tag in load(R22/"dev-graphs.json").items():
        p=n.DEV/(t+".json.gz");assert sha(p)==tag["graph_file"]
        for q,nodes in load(p)["labels"].items():positives[q]={by[q][k] for k in nodes}
    def recall(seq,yp):return len(set(seq[:5])&yp)/len(yp)
    audit={}
    for s in (13,17,29,37,41):
        ranks=load(D/f"native-{s}.json.gz")
        p=W/f"graph_memory_round21/five_seed/dev580/seed-{s}";ref=load(p/"selection.json")
        e=ref["epoch_580"];fs=load(p/f"dev580-e{e}-rows.json.gz")
        t=load(R22/f"seed-{s}"/ARM/"checkpoint.json")
        d=0;count=0;values=[]
        for q,x in ranks.items():
            v=recall(x["dense"],positives[q]);d+=abs(v-fs[q]["recall_at_5"])>1e-12
            values.append(recall(x["recall"],positives[q]))
            count+=1
        assert count==580
        audit[s]=dict(cpu_recall5=float(np.mean(values)),archived_recall5=t["metric"],dense_per_query_disagree=int(d),dense_epoch=e)
    an=load(D/"cross-packets.json.gz");raw=load(D/"packets.json.gz");gold=load(D/"dev-judgments.json.gz");summary={}
    for q,(_,panels) in an.items():
        a=raw[q][1][1];b=panels[1]
        def met(ids):
            sel=set(ids);total=sum(n for n,_ in gold[q]);hit=sum(n for n,ws in gold[q] if sel.intersection(ws))
            return int(hit==total),hit/total
        for k in a:
            old=met(a[k]);new=met(b[k]);v=summary.setdefault(k,[0,0,0])
            v[0]+=int(old[0]!=new[0]);v[1]+=new[0]-old[0];v[2]+=int(old[1]!=new[1])
    store("native-metrics-audit.json",dict(seeds=audit,second_cpu_gpu=[["full support changes","net CPU gains","character coverage changes"],summary],source=sha(Path(__file__))))
    print(audit);print(summary)
if __name__=="__main__":main()

