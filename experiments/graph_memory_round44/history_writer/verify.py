"""Verify every delivered packet and all saved hit counts without model, raw corpus, or external packages."""
from common import *
from writer import Writer
def unit():
    paths=[h("one"),h("two")];d=h("a"*26);b={d:b"a"*26};v=[[1,d,26,1]]
    for mode in MODES:
        w=Writer(mode,136);assert w.wire(b)[0]==8
        w.read(paths[0],1,v);assert w.wire(b)[0]==86
        w.read(paths[1],2,v);assert w.wire(b)[0]==136 and set(w.rows)=={(p,1) for p in paths}
        w.read(paths[1],3,[[2,d,26,1]]);assert w.wire(b)[0]<=136
        w.remove_path(paths[0]);assert all(p!=paths[0] for p,n in w.rows)
        w.clear();assert w.wire(b)[0]==8
def main():
    unit();s=read(D/"summary.json")["all"];fc=read(D/"forecast-seal.json");gc=read(D/"grade-seal.json");ip=read(D/"input-seal.json")
    assert fc["forecasts"]==sha(D/"forecasts.json.gz") and gc["rows"]==sha(D/"outcomes.json.gz")
    assert gc["forecasts"]==sha(D/"forecast-seal.json") and fc["input"]==sha(D/"input-seal.json") and ip["file"]==sha(D/"history-inputs.json.gz")
    assert all(sha(D/name)==digest for name,digest in fc["code"].items())
    assert sha(D/"grade.py")==gc["program"] and sha(D/"PROTOCOL_RU.md")==fc["protocol"]
    p=read(D/"forecasts.json.gz");o=read(D/"outcomes.json.gz");assert len(p)==len(o)==s["edits"]==2696 and set(p)==set(o)
    acc=defaultdict(Counter);wire=Counter()
    for k,v in p.items():
        r=o[k];c=v["candidates"];checks=r["checks"];assert len(c)==len(checks)
        for m,arm in v["arms"].items():
            size,n,blobs,body,digest=arm["wire"];assert size==8+50*n+2*blobs+body and len(bytes.fromhex(digest))==32
            wire[m]+=size;cap=m.split("_")[-1]
            if cap!="unlimited":assert size<=fc["peak_wire"][m]<=int(cap)
            assert set(arm["read"])<=set(arm["all"]) and len(arm["all"])==len(set(arm["all"]))
            for out in ("all","read"):
                idx=arm[out];a=r["arms"][m][out];expected=int(any(checks[i][1] and checks[i][2] for i in idx))
                assert a["hit"]==expected and a["novel_lines"]==sum(checks[i][1]*checks[i][2] for i in idx)
                assert a["bad_new"]==sum(not checks[i][1] for i in idx) and a["bad_old"]==sum(not checks[i][0] for i in idx)
                assert a["raw_bytes"]==sum(c[i][3]+1 for i in idx)
                if out=="read":assert a["raw_bytes"]==arm["emitted_bytes"]<=2048
                acc[m,out].update(a)
    for m,row in s["arms"].items():
        assert row["wire"]==wire[m]
        for t in ("all","read"):assert dict(acc[m,t])==row[t]
    if (D/"manifest.json").exists():assert all(sha(D/n)==v for n,v in read(D/"manifest.json")["files"].items())
    print("Checked",len(p),"snapshots,",len(s["arms"]),"writers and both reader settings.")
if __name__=="__main__":main()
