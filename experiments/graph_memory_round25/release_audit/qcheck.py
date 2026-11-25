from collections import Counter,defaultdict
from statistics import mean,median
from functools import lru_cache
from pathlib import Path
import json,gzip,hashlib,sqlite3,zlib,re,math,random,sys
D=Path(__file__).resolve().parent;Q=D.parent/"query_view"
def rd(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wr(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n",encoding="utf8")
def close(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-11)
WORDS=re.compile(r"[^\W_]+",re.UNICODE)
def bag(s):return Counter(WORDS.findall(s.casefold()))
def main():
    z=rd(Q/"results.json")["results"];dec=rd(Q/"decisions.json.gz");f=D.parent.parent.parent
    known={r["q"]:r for r in dec};proof=defaultdict(Counter);out={}
    snap={r["key"]:r for r in rd(Q/"cohort.json.gz")}
    db=sqlite3.connect(Path("D:/CodexResearch/x20-query-projection-sql/query-views.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    sys.path.insert(0,str(Q));import ranking
    for sid,corpus,ctx,q0,vb,ib,cb,bytes_ in db.execute("select * from snapshot order by sid"):
        view=json.loads(zlib.decompress(vb));docs=[bag(t.decode()) for t, in db.execute("select body from payload where sid=? order by idx",(sid,))]
        n=len(docs);length=[sum(d.values()) for d in docs];avg=sum(length)/n or 1;df=Counter(w for doc in docs for w in doc)
        assert dict(df)==view["df"]
        caps=set(view["first"])
        for i,(doc,meta) in enumerate(zip(docs,view["rows"])):
            assert meta["length"]==length[i] and meta["known"]=={k:v for k,v in doc.items() if k in caps}
            assert meta["unknown_max"]==max([0]+[v for k,v in doc.items() if k not in caps])
            assert all(meta["bits"]&ranking.mask(k)==ranking.mask(k) for k in doc)
        for q,x in db.execute("select q,question from future where sid=?",(sid,)):
            outcome=known[q];assert q!=q0 and sid==outcome["g"]
            words=sorted(set(bag(x))&set(df));scores=[];el=[]
            for i,(doc,m) in enumerate(zip(docs,view["rows"])):
                if not m["coords"][-1]:continue
                el.append(i);weights=[math.log1p((n-df[w]+.5)/(df[w]+.5)) for w in words]
                norm=1.2*(.25+.75*length[i]/avg)
                def score(freq):return sum(u*freq(w)*2.2/(freq(w)+norm) for u,w in zip(weights,words) if freq(w))
                true=score(lambda w:doc[w]);bound=score(lambda w:(doc[w] if w in caps else m["unknown_max"] if m["bits"]&ranking.mask(w)==ranking.mask(w) else 0))
                assert true<=bound+1e-12
                proof[corpus]["candidates"]+=1;scores.append((true,-i,i))
            ref=max(scores)[2] if scores else None
            assert ref==outcome["ref"]
            if sum(k[0]==max(s[0] for s in scores) for k in scores)>1:proof[corpus]["ties"]+=1
            for k,v in outcome["arms"].items():
                if k!="projected":assert v[0]==ref
            proof[corpus]["queries"]+=1
    db.close()
    timing=rd(Q/"hydrate-times.json.gz");hyd=rd(Q/"hydrate-results.json")["summary"]
    for corp,nums in z.items():
        arr=[r for r in dec if r["c"]==corp];groups={r["g"] for r in arr}
        assert len(arr)==nums["queries"] and len(groups)==nums["snapshots"]
        for m,total in nums["summary"].items():
            n=len(arr);readsum=sum(r["arms"][m][3] for r in arr);metadata=sum(snap[s]["index_bytes"][m] for s in groups)
            assert metadata==total["metadata_bytes"] and readsum==total["total_source_bytes"]
            assert readsum+metadata==total["write_plus_read_bytes"]
            assert sum(r["arms"][m][1]==r["arms"]["scan"][1] for r in arr)==total["exact_address"]
            sel=[r for r in timing if r[0]==corp and r[3]==m and r[4]==0]
            assert all(v[6]==known[v[2]]["arms"][m][3]+known[v[2]]["size"][m] for v in sel)
            assert close(mean(v[6] for v in sel),hyd[corp][m]["mean_sql_bytes"])
        out[corp]=dict(proof[corp])
    rng=random.Random(2512);fixtures=0
    for n in range(1,27):
        for rep in range(30):
            wins=[dict(e=i,l=0,h=4,edge=4,eligible=bool(rng.randrange(4)),text=" ".join(rng.choices(("a","b","c","d"),k=rng.randrange(11)))) for i in range(n)]
            v,docs=ranking.write_view(wins,rng.choice(("","a b","a")));q=rng.choice(("a","e","b c","a b c d",""))
            ref=ranking.select(v,q,"scan",lambda i:docs[i])
            for k in ("bloom_lazy","bloom_cold","bloom_scan","exact_lazy","df_scan"):
                assert ref==ranking.select(v,q,k,lambda i:docs[i])
            fixtures+=1
    nextrows=rd(Q/"next-outcomes.json.gz");goldres=rd(Q/"next-results.json")["summary"]
    for corpus,panel in nextrows.items():
        for k in list(next(iter(panel.values()))["outcomes"]):
            vs=[r["outcomes"][k] for r in panel.values()];s=goldres[corpus]["metrics"][k]
            assert sum(z[0] for z in vs)==s["hits"] and close(mean(z[1] for z in vs),s["coverage"]) and close(mean(z[2] for z in vs),s["tokens"])
    report={"full":out,"adversarial_fixtures":fixtures,"decision_h":sha(Q/"decisions.json.gz"),"next_h":sha(Q/"next-outcomes.json.gz"),"hydrate_h":sha(Q/"hydrate-times.json.gz")};wr(D/"query-checks.json",report);print(report)
if __name__=="__main__":main()
