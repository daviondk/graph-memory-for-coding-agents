"""Project a deterministic panel from the frozen R39 reader and public ISETrace objects."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

D = Path(__file__).resolve().parent
W = D.parents[1]
sys.path.insert(0,str(D.parent/"global_packet"))
import packet
sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
import data as upstream
from graph_memory.datasets.isetrace.adapter import adapt_isetrace_record, parse_isetrace_record

read, sha = packet.read, packet.sha

def key(s): return hashlib.sha256(s.encode()).hexdigest()

def save(name, data):
    payload=(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False)+"\n").encode()
    path=OUT/name
    if path.exists(): assert path.read_bytes()==payload, name
    else: path.write_bytes(payload)

def source(span): return key(json.dumps([span["event_id"],span["json_pointer"]],separators=(",",":")))

def build():
    pp=D.parent/"global_packet";forecast=read(pp/"test-13-pred.json.gz");selection={};used=set()
    for q in sorted(forecast,key=lambda q:key("r39-source-demo-v1|"+q)):
        t=forecast[q][0]
        if t in used:continue
        selection[q]=t;used.add(t)
        if len(selection)==40:break
    panel={q:f"q{i:02}" for i,q in enumerate(selection,1)}
    save("panel.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),revision=upstream.nm.pilot.RAW[1],queries=[dict(number=panel[q],query=key(q),trajectory=key(t)) for q,t in selection.items()],prediction_file=sha(pp/"test-13-pred.json.gz"),model=sha(pp/"models.json"),dev_selection=sha(pp/"dev-selection.json")))
    assert read(pp/"dev-selection.json")["thresholds"]["graph"]==1024
    index,x=packet.projections("test",13); model=read(pp/"models.json")["models"]["graph"]; np=packet.np
    records={}; shard_hashes={}
    for path in upstream.sources("test"):
        shard_hashes[path.name]=sha(path)
        for obj in read(path):
            if obj["q"] in selection:records[obj["q"]]=obj
    assert records.keys()==selection.keys()
    graphs=upstream.f.gmod.graph_index(); trajectory_by_id={}; rawmeta={}; rawdir=Path(upstream.nm.pilot.Q).parents[1]/"trajectories"
    lock=read(upstream.nm.OFF/"source-lock.json");locks={o["path"]:o["sha256"] for o in lock}
    pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"'); raw_shards={}
    for path in sorted(rawdir.glob("trajectories-*.jsonl")):
        full=hashlib.sha256()
        with path.open("rb") as f:
            for buf in f:
                full.update(buf);m=pattern.search(buf)
                if not m:continue
                t=m.group(1).decode()
                if t not in used:continue
                parsed=adapt_isetrace_record(parse_isetrace_record(json.loads(buf)),source_revision=upstream.nm.pilot.RAW[1]);assert parsed.trajectory_id==t
                trajectory_by_id[t]={e.event_id:e for e in parsed.events}
                rawmeta[t]=hashlib.sha256(buf).hexdigest()
        assert full.hexdigest()==locks["trajectories/"+path.name];raw_shards[path.name]=full.hexdigest()
    assert set(trajectory_by_id)==used
    db=sqlite3.connect(OUT/"reader.sqlite"); gdb=sqlite3.connect(OUT/"grader.sqlite")
    db.executescript("""CREATE TABLE query(q TEXT PRIMARY KEY, query_hash TEXT, trajectory_hash TEXT); CREATE TABLE node(q TEXT,id INTEGER, node_hash TEXT, role TEXT, tokens INTEGER, rank INTEGER, utility REAL, PRIMARY KEY(q,id)); CREATE INDEX ranked ON node(q,rank); CREATE TABLE span(q TEXT,id INTEGER,source TEXT,lo INTEGER,hi INTEGER,PRIMARY KEY(q,id,source,lo,hi)); CREATE INDEX by_source ON span(q,source,id); CREATE TABLE origin(q TEXT,source TEXT,role TEXT,position INTEGER,length INTEGER, digest TEXT, PRIMARY KEY(q,source)); CREATE TABLE edge(q TEXT, left_node TEXT,right_node TEXT,relation TEXT);CREATE INDEX edge_left ON edge(q,left_node);CREATE INDEX edge_right ON edge(q,right_node);""")
    gdb.executescript("CREATE TABLE gold(q TEXT,source TEXT,lo INTEGER,hi INTEGER);CREATE INDEX goldq ON gold(q);")
    spans=nodes=edges=0;refs={};proof=[]
    gold=read(upstream.nm.OFF/"gold-spans.json.gz");actual=read(pp/"test-13-outcomes.json.gz")
    for q,t in selection.items():
        qp=panel[q];row=records[q];assert row["t"]==t
        traj=trajectory_by_id[t];gp,ghash=graphs[t];assert sha(gp)==ghash;graph=read(gp);assert graph["raw_source"]==rawmeta[t]
        gd=graph["g"];by_node={v["node_id"]:v for v in gd["nodes"]};source_info={};t0,c,order,_,sl=index[q];assert t0==t
        utility=np.logaddexp(0, packet.portable(model,x[sl][:,model["cols"]])); ranks=np.argsort(order)
        db.execute("INSERT INTO query VALUES(?,?,?)",(qp,key(q),key(t))); rr=row["rr"]
        for i,v in enumerate(rr):
            native=by_node[v["node_id"]];assert v["token_count"]==c[i] and native["source_spans"]==v["source_spans"]
            db.execute("INSERT INTO node VALUES(?,?,?,?,?,?,?)",(qp,i,key(v["node_id"]),native["kind"],int(c[i]),int(ranks[i]),float(utility[i])));nodes+=1
            for s in v["source_spans"]:
                e=traj[s["event_id"]]; pointer=s["json_pointer"]; assert pointer in {"/raw_arguments","/content"}
                body=getattr(e,pointer[1:]);a,b=s["char_start"],s["char_end"];assert 0<=a<b<=len(body)
                h=source(s);source_info[h]=(qp,h,e.event_type,e.position.message_index,len(body),key(body)); db.execute("INSERT INTO span VALUES(?,?,?,?,?)",(qp,i,h,a,b));spans+=1
        db.executemany("INSERT INTO origin VALUES(?,?,?,?,?,?)",source_info.values())
        for edge in gd["edges"]:
            db.execute("INSERT INTO edge VALUES(?,?,?,?)",(qp,key(edge["source"]),key(edge["target"]),edge["relation"]));edges+=1
        for s in gold[q]:
            h=source(s);e=traj[s["event_id"]];body=getattr(e,s["json_pointer"][1:]);a,b=s["char_start"],s["char_end"];assert 0<=a<b<=len(body)
            gdb.execute("INSERT INTO gold VALUES(?,?,?,?)",(qp,h,a,b))
        refs[qp]=dict(ids=forecast[q][1]["graph-dp"],official=actual[q][1]["graph-dp"]);proof.append(dict(query=qp,graph_sha=ghash,raw_record_sha=rawmeta[t]))
    db.commit();gdb.commit();db.close();gdb.close()
    save("reference.json",refs);save("provenance.json",dict(raw_shards=raw_shards,candidate_shards=shard_hashes,trajectory_checks=proof,nodes=nodes,spans=spans,edges=edges,gold=sha(upstream.nm.OFF/"gold-spans.json.gz"),native_outcomes=sha(pp/"test-13-outcomes.json.gz"),databases={f:sha(OUT/f) for f in ("reader.sqlite","grader.sqlite")}))
    print(len(panel),nodes,spans,edges,flush=True)

if __name__=="__main__":
    OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else D
    OUT.mkdir(exist_ok=True,parents=True)
    if any((OUT/name).exists() for name in ("reader.sqlite","grader.sqlite")):raise SystemExit("select a fresh output directory")
    build()
