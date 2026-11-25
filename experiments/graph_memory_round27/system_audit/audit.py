"""Read-only audit of SQL BM25 decisions, exact byte accounting, actual route order, LRU and timing receipts."""
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median, mean, quantiles
import gzip,hashlib,json,math,re,sqlite3,zlib
D=Path(__file__).resolve().parent;WC=D.parent/"write_cost";WK=D.parent/"worker_cache"
ST=Path("D:/CodexResearch/x20-query-projection-sql");J=ST/"query-views.sqlite";I=ST/"terms.sqlite"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(p,x):
    b=(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(n):return hashlib.sha256(n.encode()).hexdigest()
def ro(p):return sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
def tokens(s):return Counter(re.findall(r"[^\W_]+",s.casefold()))
def group_query(questions,docs,eligible):
    n=len(docs);sizes=[sum(d.values()) for d in docs];avg=sum(sizes)/n or 1
    df=Counter(term for d in docs for term in d)
    out={}
    for key,text in questions:
        q=sorted(tokens(text));weights={w:math.log((n+.5-df[w])/(df[w]+.5)+1) for w in q if df[w]}
        scores=[]
        for k in eligible:
            # Direct dense scoring over the raw windows without the project's postings or scorer.
            norm=1.2*.25+1.2*.75*sizes[k]/avg
            scores.append((sum(weights[w]*(2.2*docs[k][w])/(docs[k][w]+norm) for w in weights if docs[k][w]),-k))
        out[key]=-max(scores)[1] if scores else None
    return out
def main():
    db=ro(J);ix=ro(I);plan=read(WC/"plan.json");schedule=read(WK/"schedule.json")
    assert sha(J)==plan["source"]==schedule["journal"] and sha(I)==schedule["index"]
    groups=plan["cohort"];known={};bodies={};header={};post={};questions={};extra={}
    for episode,corpus in groups:
        obj=json.loads(zlib.decompress(db.execute("select projected from snapshot where sid=?",(episode,)).fetchone()[0]))
        body=[r[0] for r in db.execute("select body from payload where sid=? order by idx",(episode,))];docs=[tokens(s.decode()) for s in body]
        rows=obj["rows"];assert len(docs)==len(rows) and [sum(d.values()) for d in docs]==[d["length"] for d in rows]
        qs=list(db.execute("select q,question from future where sid=?",(episode,)))
        answers=group_query(qs,docs,[j for j in range(len(rows)) if rows[j]["coords"][4]])
        for q,t in qs:
            known[episode,q]=answers[q];questions[episode,q]=set(tokens(t))
        bodies[episode]=sum(map(len,body))
        if corpus=="squad":
            s,blob=ix.execute("select id,header from snapshots where name=?",(episode,)).fetchone()
            coords,lens=json.loads(zlib.decompress(blob));assert coords==[r["coords"] for r in rows] and lens==[sum(d.values()) for d in docs]
            header[episode]=len(blob)
            post[episode]={t:len(t.encode())+len(blob) for t,blob in ix.execute("select term,postings from terms where id=?",(s,))}
    assert len(known)==624 and len(groups)==144
    timings={};stable={};stats={}
    for pfx in ("","promotion-"):
        series=read(WC/(pfx+"times.json.gz"));made=read(WC/(pfx+"receipt.json"))
        assert made["times"]==sha(WC/(pfx+"times.json.gz"))
        measured=defaultdict(list);reps=defaultdict(list);verified=0
        for rep,corp,s,m,start,entries in series:
            cost=start;traffic=0;reps[corp,s,m,0].append((cost,traffic))
            for n,(q,ns,b,win) in enumerate(entries,1):
                assert known[s,q]==win;verified+=1;cost+=ns;traffic+=b
                reps[corp,s,m,n].append((cost,traffic))
        for (corp,s,m,n),vec in reps.items():
            assert len(vec)==3
            measured[corp,n,m].append((s,median(a for a,b in vec),median(b for a,b in vec)))
        published=read(WC/(pfx+"results.json"))["samples"];cells=0
        for code,by in published.items():
            corp,n=code.split("/");n=int(n)
            for m,vals in by.items():
                arr=measured[corp,n,m];ns=[a for _,a,_ in arr];rates=[b for _,_,b in arr]
                assert abs(vals["mean_total_ms"]-mean(ns)/1e6)<1e-8 and abs(vals["p50_total_ms"]-median(ns)/1e6)<1e-8
                assert abs(vals["mean_payload_bytes"]-mean(rates))<1e-9;cells+=1
        own={};trajectory=[]
        for s,corp in groups:
            if corp!="squad":continue
            ds=[median(x for x,y in reps[corp,s,"eager",n])-median(x for x,y in reps[corp,s,"raw",n]) for n in range(12)]
            ever=next((n for n,x in enumerate(ds) if x<0),None)
            stable_n=max((n for n,x in enumerate(ds) if x>=0),default=-1)+1
            own[s]=[ever,stable_n if stable_n<=11 else None];trajectory.append([int(ds[n]<0) for n in range(12)])
        stable[pfx or "main"]=own
        counts={n:sum(t[n] for t in trajectory) for n in range(12)}
        stats[pfx or "main"]={"answers_checked":verified,"timing_cells":cells,"squad_articles_eager_faster_by_query_count":counts,
             "observed_stable_crossings":dict(Counter(v[1] for v in own.values()))}
    claimed=read(WC/"crossover.json")["per_article"]
    assert {s:stable["main"][s]+stable["promotion-"][s] for s in stable["main"]}==claimed
    cases=read(WK/"responses.json.gz");rec=read(WK/"receipt.json")
    assert len(cases)==rec["actual"]==22176 and sha(WK/"responses.json.gz")==rec["responses"]
    article_order=sorted(header,key=lambda s:digest("worker-locality-v1/"+s));stream=[]
    for group in range(0,48,8):
        for step in range(11):
            for pos,s in enumerate(article_order[group:group+8]):
                ids=sorted([q for e,q in known if e==s],key=lambda q:digest("worker-locality-v1/"+q))
                stream.append([s,ids[step],pos%4,(pos+step)%4])
    assert stream==schedule["order"];assert all(len(set(r[1] for r in stream))==528 for _ in [0])
    # Use a last-access timestamp and "evict minimum" rather than the service's OrderedDict.
    buckets=defaultdict(list)
    for r in cases:buckets[tuple(r[:4])].append(r)
    repeated=defaultdict(lambda:defaultdict(list));hits={};ways={};summary={}
    for (rep,m,cap,route),rec_rows in buckets.items():
        assert len(rec_rows)==528
        state=[{} for _ in range(4)];terms=[{} for _ in range(4)];by_worker=Counter()
        for t,(r,(s,q,fixed,rotating)) in enumerate(zip(rec_rows,stream)):
            worker=fixed if route=="affine" else rotating
            _,_,_,_,sid,qid,w,winner,wire,body,miss,service,rpc=r
            assert [sid,qid,w,winner]==[s,q,worker,known[s,q]];by_worker[w]+=1
            stamps=state[w];cache=terms[w];cold=s not in stamps
            assert cold==bool(miss)
            if cold:cache[s]=set()
            payload=bodies[s] if cold and m=="raw_cache" else 0
            sql=header[s]*int(cold)+payload
            if m!="raw_cache":
                missing=questions[s,q]-cache[s]
                sql+=sum(post[s].get(term,0) for term in missing);cache[s].update(missing)
            assert sql==wire and body==payload and rpc>=service>=0
            if m!="shared_sql":
                stamps[s]=t
                if len(stamps)>cap:
                    expired=min(stamps,key=stamps.get);del stamps[expired];del cache[expired]
            else:cache.clear()
            repeated[m,cap,route][s,q].append((wire,payload,miss,service,rpc))
        assert sorted(by_worker.values())==[132]*4
    pub=read(WK/"results.json")
    for k,values in repeated.items():
        m,cap,route=k
        tag="/".join(map(str,k));three=list(values.values())
        assert len(three)==528 and all(len(x)==3 for x in three)
        ns=[median(r[4] for r in sample)/1000 for sample in three]
        cold=sum(sample[0][2] for sample in three)
        assert cold==pub[tag]["misses"] and abs(median(ns)-pub[tag]["p50_rpc_us"])<1e-8
        assert abs(quantiles(ns,n=100,method="inclusive")[94]-pub[tag]["p95_rpc_us"])<1e-8
        assert abs(mean(sample[0][0] for sample in three)-pub[tag]["mean_sql_bytes"])<1e-9
        summary[tag]={"misses":cold,"mean_payload":mean(sample[0][1] for sample in three),"mean_sql_bytes":mean(sample[0][0] for sample in three)}
    assert len(buckets)==42 and len(repeated)==14
    # Concrete witness: same requests, same overall duration if inter-arrival times are fixed.
    a=summary["raw_cache/4/affine"];b=summary["raw_cache/4/rotate"]
    fingerprints={p.name:sha(p) for p in (WC/"times.json.gz",WC/"promotion-times.json.gz",WK/"responses.json.gz",WK/"schedule.json")}
    save(D/"audit-results.json",dict(source_sha={J.name:sha(J),I.name:sha(I)},receipts_sha=fingerprints,
        total_exact_queries=len(known),corpus_sizes={"ISETrace":96,"SQuAD":528},timing_panels=stats,workers=summary,
        worker_decisions_checked=len(cases),worker_wire_bytes_checked=len(cases),worker_lru_decisions_checked=len(cases),
        temporal_witness={"same_ordered_episode_question_stream":528,"four_workers_each_questions":132,"groups":6,"active_articles_per_group":8,
                          "rounds_per_group":11,"capacity":4,"affine_misses":a["misses"],"rotate_misses":b["misses"],
                          "clock_not_input_to_routing_or_cache":True},code=sha(Path(__file__))))
    db.close();ix.close();print("Exact",len(known),"worker records",len(cases),stats)
if __name__=="__main__":main()
