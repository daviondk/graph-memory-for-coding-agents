"""Verify the main claims and physical GPU calls from saved responses."""
import gzip, json, hashlib, collections, sys
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def main():
    root={}
    for name,expected in [("reader/A",672),("reader/B",171),("reader/C0",90),("reader/C",185),("reader/F",239),("reader/G_fresh/G",21),("crosscode/D",216),("crosscode/E",184),("next_action/H",226)]:
        prefix=R/name
        lock=read(prefix.parent/(prefix.name+"_decisions.json"));ix=read(prefix.parent/(prefix.name+"_assignment.json"))
        assert len(lock)==expected and set(lock)=={v+".json.gz" for row in ix.values() for v in row.values()}
        tokens=collections.Counter()
        for n,h in lock.items():
            f=prefix.parent/(prefix.name+"_calls")/n
            assert sha(f)==h,n
            record=read(f); reply=record["reply"]
            for k in ("prompt_tokens","completion_tokens"):tokens[k]+=reply["usage"][k]
        root[name]=dict(physical_calls=len(lock),tasks=len(ix),tokens=dict(tokens),sha=sha(prefix.parent/(prefix.name+"_decisions.json")))
    A,B,C,F=[read(R/"reader"/(v+"_packets.json.gz")) for v in "ABCF"]
    pa,pb,pc,pf=[{x["repo"] for x in vals} for vals in (A,B,C,F)]
    assert len(pa)==128 and len(pb)==64 and len(pc)==90 and pa==pf and not(pa&pb or pb&pc or pa&pc)
    e=read(R/"crosscode/E_results.json");d=read(R/"crosscode/D_results.json")
    assert (e["usable"]["n"],e["changed"],e["counts"]["order"],e["counts"]["bridge"])==(2139,92,29,26)
    w=read(R/"action_probe/bounded_results.json"); t=read(R/"action_transfer/results.json")
    assert (w["n"],w["counts"]["base"],w["counts"]["address"],w["counts"]["lru_address"])==(253,112,173,172)
    assert (t["funnel"]["evaluable"],*[t["methods"][a]["hits"] for a in ("cap_base","cap_address","cap_lru_address")])==(206,73,121,119)
    roster=lambda path:{x["id"] if isinstance(x,dict) else x for x in read(path)}
    # Cross-check project membership using original projected streams, independent of roster serialization.
    def stream_ids(d):
        ids=set()
        for p in sorted(d.glob("source_*.jsonl.gz")):
            with gzip.open(p,"rt",encoding="utf8") as f:ids.update(v["instance"] for v in map(json.loads,f))
        return ids
    orig=stream_ids(R/"writer"); fresh=stream_ids(R/"action_transfer")
    assert len(orig)==112 and len(fresh)==98 and not orig&fresh
    res=dict(gpu=root,physical_calls=sum(d["physical_calls"] for d in root.values()),tokens={k:sum(d["tokens"][k] for d in root.values()) for k in ("prompt_tokens","completion_tokens")},verified_repo_panels=[len(pa),len(pb),len(pc)],writer_replication_disjoint=True)
    (R/"run_totals.json").write_text(json.dumps(res,indent=2),encoding="utf8")
    print(res["physical_calls"],res["tokens"])
if __name__=="__main__":main()

