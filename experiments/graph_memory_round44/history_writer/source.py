"""Capture eligible observed reads up to but never beyond each run's last requested action."""
import importlib.util
import pyarrow.parquet as pq
from common import *

def capture(cases):
    limit={}
    for r in cases:limit[r["run"]]=max(limit.get(r["run"],-1),r["at"])
    corpus=signed(H,"events.json.gz");bounds=signed(E,"native_boundaries.json.gz")
    events={};needed=defaultdict(dict)
    for rid,end in limit.items():
        frames=[]
        for e in corpus[rid]["events"]:
            at,kind=e[:2]
            if at>end:continue
            path=h(e[2]) if len(e)>2 else ""
            if kind=="read":
                needed[rid][at]=(list(e[3]),path)
            frames.append([at,kind,path])
        for a,b in bounds[rid]["gaps"]:
            if a+.5<=end:frames.append([a+.5,"gap",""])
        if bounds[rid]["finished"] is not None and bounds[rid]["finished"]<=end:frames.append([bounds[rid]["finished"],"finish",""])
        events[rid]=sorted(frames)
    del corpus,bounds
    sys.path.insert(0,str(V))
    # Load the existing display gate using a distinct name before any raw receipt is opened.
    from detector import gate
    from examine import display
    reads=defaultdict(dict);bodies={};memo={};stats=Counter()
    for part in read(RAW/"files.json")["events"]:
        f=RAW/part["file"];assert sha(f)==part["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for k,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in memo:memo[run]=h(run)
                rid=memo[run]
                if rid not in needed or at not in needed[rid]:continue
                labels,path=needed[rid][at];labels=dict(labels)
                observation=json.loads(batch.column(2)[k].as_py())["raw"]["observation"]
                ob={key:observation[key] for key in ("command","path","is_error","content")}
                assert ob["command"]=="view" and not ob["is_error"] and h(ob["path"].removeprefix("/testbed/").removeprefix("/workspace/"))==path
                text,_,_=display(ob);allowed,_=gate(ob);view=[]
                for n,line in text.items():
                    if not allowed[n][2]:continue
                    body=line.encode();dg=hashlib.sha256(body).hexdigest();ok=labels.get(n)==dg
                    if ok:
                        if dg in bodies:assert bodies[dg]==body
                        else:bodies[dg]=body
                    view.append([n,dg,len(body),int(ok)])
                reads[rid][at]=view;stats.update(dict(views=1,informative=sum(x[3] for x in view),trusted_display_rows=len(view)))
    assert all(set(q)==set(reads[r]) for r,q in needed.items())
    save("history-inputs.json.gz",dict(events=events,reads=reads))
    save("input-seal.json",dict(file=sha(D/"history-inputs.json.gz"),cases=sha(G/"selections.json.gz"),sources={x:sha(p) for x,p in
        (("parquet",RAW/"files.json"),("timeline",H/"events.json.gz"),("bounds",E/"native_boundaries.json.gz"),("gate",V/"detector.py"))},
        stats=stats,runs=len(events),actions=len(cases),unique_literal_bodies=len(bodies),raw_body_bytes=sum(map(len,bodies.values())),program=sha(D/"source.py")))
    return events,reads,bodies

