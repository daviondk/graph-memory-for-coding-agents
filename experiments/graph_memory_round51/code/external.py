"""Independent public Test500 transport replication with four fixed codecs and repository bootstrap."""
from columns import *
PROTO_TEST="6cce475ef8d222ea53f7edad19665e10c770dacac1e8335f17b08ec9e4e7cf9d"
TAGS=(5,17,24,25)

def measures(rows,qs):
    repos=sorted({rows[q]["repo"] for q in qs})
    by=np.array([np.sum([rows[q]["bytes"] for q in qs if rows[q]["repo"]==r],axis=0) for r in repos])
    boot=np.random.default_rng(510314).multinomial(len(repos),np.full(len(repos),1/len(repos)),size=20000)@by
    total=by.sum(0)
    ci=np.quantile(1-boot[:,3]/boot[:,2],[.025,.975]).tolist()
    return dict(states=len(qs),repos=len(repos),bytes=total.tolist(),saving=1-total[3]/total[2],ci=ci,
        wins=sum(rows[q]["bytes"][3]<rows[q]["bytes"][2] for q in qs),losses=sum(rows[q]["bytes"][3]>rows[q]["bytes"][2] for q in qs),
        derivable=sum(rows[q]["derivable"] for q in qs),fragments=sum(rows[q]["count"] for q in qs))

def run():
    assert sha(HERE/"TEST500_PROTOCOL_RU.md")==PROTO_TEST
    inp=UPSTREAM/"data/test500/items.jsonl.gz"
    ranks=EXPERIMENTS/"graph_memory_round39/blind_export/author_baseline/test500-lexical-residual.jsonl"
    lineage=EXPERIMENTS/"graph_memory_round50/cache_replication/test-panel.json.gz"
    lin=read(lineage)
    with ranks.open(encoding="utf8") as f:
        ranks_by_id={r["state_id"]:r["ranked_evidence_ids"][:8] for r in map(json.loads,f) if r["ranked_evidence_ids"]}
    assert lin.keys()==ranks_by_id.keys() and len(lin)==491
    with gzip.open(inp,"rt",encoding="utf8") as f:
        items={r["state_id"]:r for r in map(json.loads,f) if r["state_id"] in lin}
    cal=read(HERE/"inputs.json.gz")
    assert not set(lin)&set(cal) and not {r["repo"] for r in cal.values()}&{v["repo"] for v in lin.values()}
    decoded={};out={}
    for q,meta in sorted(lin.items(),key=lambda t:(len(t[1]["prior"]),t[0])):
        raw={v["evidence_id"]:v for v in items[q]["candidate_evidence"]}
        actual=[[raw[i].get(k) for k in FIELDS] for i in ranks_by_id[q]]
        assert len(actual)==8
        p=meta["prior"][-1] if meta["prior"] else None
        prev=decoded[p] if p else []
        if p:
            assert lin[p]["step"]<meta["step"] and lin[p]["scope"]==meta["scope"]
        frames=[selected_encode(actual,prev,i) for i in TAGS]
        for f in frames:
            restored=selected_decode(f,prev);assert restored==actual
        decoded[q]=restored
        out[q]=dict(repo=meta["repo"],parent=p,count=len(actual),derivable=sum(derivable(v[5],v[6]) for v in actual),
            canonical=hashlib.sha256(packed(actual)).hexdigest(),bytes=list(map(len,frames)),wire=[hashlib.sha256(f).hexdigest() for f in frames])
    summary={p:measures(out,qs) for p,qs in [("all",list(out)),("warm",[q for q,r in out.items() if r["parent"]])]}
    return out, dict(panels=summary,modes=TAGS,decodes=len(out)*len(TAGS),program=sha(HERE/"external.py"),protocol=PROTO_TEST,
        source_digests=dict(items=sha(inp),ranks=sha(ranks),lineage=sha(lineage),codec=sha(HERE/"columns.py")))
if __name__=="__main__":
    rows,stats=run()
    save("external-records.json.gz",rows)
    stats["records"]=sha(HERE/"external-records.json.gz")
    save("external-results.json",stats)
    print(json.dumps(stats["panels"]))

