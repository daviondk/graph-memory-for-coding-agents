import collections
import gzip
import json
import numpy as np
from predict import HERE,digest,dump
from score import GOLD,SourceSpan,RankedNodeRecord,take,ci

def main():
    lock=json.loads((HERE/"graph-lock.json").read_bytes())
    assert digest(HERE/"graph_write.py")==lock["generator"] and digest(HERE/"GRAPH_PROTOCOL_RU.md")==lock["protocol"]
    assert digest(HERE/"forecast-lock.json")==lock["inputs"]
    truth={q:tuple(SourceSpan(**x) for x in s) for q,s in json.load(gzip.open(GOLD,"rb")).items()}
    old={x["q"]:x["a"]["head/8192"] for x in json.load(gzip.open(HERE/"outcomes.json.gz","rb"))}
    rows=[]
    edge_stats=collections.Counter(); marginal=collections.Counter(); moved=collections.Counter()
    for i in range(8):
        gpath=HERE/f"graph-{i}.jsonl.gz"
        assert digest(gpath)==lock["forecasts"][gpath.name]
        with gzip.open(gpath) as graphs,gzip.open(HERE/f"forecast-{i}.jsonl.gz") as originals:
            for l,m in zip(graphs,originals,strict=True):
                g,r=json.loads(l),json.loads(m)
                assert r["t"]==g["t"]
                edge_stats.update(g["stats"])
                nodes=[]
                for j,(e,a,b,c,nbytes) in enumerate(r["blocks"]):
                    eid,ptr=r["addresses"][e]
                    s=SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b)
                    nodes.append(RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(s,)))
                baseline=set(r["arms"]["head/8192"][0])
                scores={}
                for arm,(keep,reads) in dict(g["arms"],head=r["arms"]["head/8192"]).items():
                    marginal.update((arm,g["roles"][r["blocks"][j][0]]) for j in keep)
                    moved[arm]+=len(set(keep)^baseline)
                    kept=[nodes[j] for j in keep]
                    assert sum(n.token_count for n in kept)<=8192
                    for q,sel in reads.items():
                        assert set(sel)<=set(keep)
                        read=[nodes[j] for j in sel]
                        assert sum(n.token_count for n in read)<=2048
                        score=take(kept,truth[q],False)+take(read,truth[q],False)
                        if arm=="head": assert np.allclose(score,old[q][:6],rtol=0,atol=1e-12)
                        scores.setdefault(q,{})[arm]=score
                for q,arms in scores.items():
                    call_roles=collections.defaultdict(set)
                    for s in truth[q]:
                        if s.event_id in g["calls"]:
                            call_roles[g["calls"][s.event_id]].add(s.json_pointer)
                    paired=any({"/content","/raw_arguments"}<=v for v in call_roles.values())
                    rows.append(dict(q=q,t=r["t"],paired=paired,a=arms))
    assert len(rows)==2000 and len({r["q"] for r in rows})==2000
    out={}
    for label,sub in [("all",rows),("paired",[r for r in rows if r["paired"]]),("unpaired",[r for r in rows if not r["paired"]])]:
        out[label]=dict(n=len(sub),means={a:np.mean([r["a"][a] for r in sub],axis=0).tolist()
            for a in ("head","shared","shifted")},comparisons={f"shared-{b}/{name}":ci(sub,("shared",b),k)
            for b in ("shifted","head") for name,k in (("write_FS",0),("read_FS",3))}) if sub else dict(n=0)
    out["edge_stats"]=dict(edge_stats)
    out["retained_blocks_by_arm_and_role"]={a+"/"+b:n for (a,b),n in marginal.items()}
    out["symmetric_difference_blocks_vs_head"]=dict(moved)
    (HERE/"graph-outcomes.json.gz").write_bytes(gzip.compress(dump(rows).encode(),mtime=0))
    (HERE/"graph-results.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    main()

