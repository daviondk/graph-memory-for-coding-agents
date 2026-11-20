"""Score the fixed-batch transfer in downstream generation."""
from score5 import *
from original_targets import gold_rows
def main():
    k="F";sealed(k);info=read("F_packets.json.gz");groups=defaultdict(dict);out=[]
    for x in info:groups[x["file"]][x["local_index"]]=x
    for f,idx in groups.items():
        for j,r in enumerate(gold_rows(P/"archive_inputs"/f)):
            if j not in idx:continue
            x=idx[j];ref=r["next_line"].strip();goldidx=r["gold_snippet_index"]
            m=metrics_per_row(k,x,ref,goldidx)
            for a,v in m.items():
                v["hit"]=int(goldidx in x["rank"][:x["depths"][a]]);v["slots"]=x["depths"][a]
            out.append(dict(id=x["id"],repo=x["repo"],panel=x["panel"],block=x["block"],methods=m,gold=ref,gold_index=goldidx))
    assert len(out)==len(info)==len({x["repo"] for x in out})
    def summary(z):
        return dict(n=len(z),totals={a:{f:sum(x["methods"][a][f] for x in z) for f in ["em","hit","slots","prompt_tokens","snippet_tokens","reply_tokens"]} for a in ["fixed","budget"]},contrast={m:compare(z,"budget","fixed",m) for m in ["em","hit","id_f1","es"]})
    hashes={h for v in sealed(k).values() for h in v.values()}; total={f:sum(get(k,h)[0]["usage"][f] for h in hashes) for f in ["prompt_tokens","completion_tokens"]}
    res=dict(all=summary(out),strata={p:summary([x for x in out if x["panel"]==p]) for p in sorted({x["panel"] for x in out})},blocks={str(b):summary([x for x in out if x["block"]==b]) for b in range(4)},physical_calls=len(hashes),tokens=total)
    save("F_items.json.gz",out);save("F_results.json",res)
    print(res["all"],flush=True)
if __name__=="__main__":main()

