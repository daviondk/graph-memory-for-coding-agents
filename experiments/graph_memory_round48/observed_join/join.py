"""Join sealed numeric fixtures to exact in-memory archive fields; no execution of archive content."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import sys

D=Path(__file__).resolve().parent
W=D.parents[1]
R39=W/"graph_memory_round39/provenance_packet_demo"
R44=W/"graph_memory_round44/sql_flow"
FLOW=R44.parent/"flow_view"
R46=W/"graph_memory_round46/trust_view"

def sha(b):return hashlib.sha256(b).hexdigest()
def compact(x):return json.dumps(x,separators=(",",":"),sort_keys=True).encode()
def digest(p):return sha(p.read_bytes())
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(name,x):
    b=compact(x)+b"\n"
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def db(p):return sqlite3.connect(p.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
def field(event,pointer):return sha(compact([event.event_id,pointer]))

def select(nodes,active):
    import numpy as np
    rows=[(i,c,u) for i,c,u in nodes if i in active]
    result=[];capacity=2048
    for i,c,u in rows:
        if capacity-c<1024:break
        capacity-=c;result.append(i)
    tail=rows[len(result):]
    best=np.zeros(capacity+1,dtype=np.int64); decisions=[]
    for i,c,u in tail:
        if c>capacity:continue
        avail=best[:capacity+1-c]+u
        take=avail>best[c:]
        np.maximum(avail,best[c:],out=best[c:])
        decisions.append((c,i,take))
    picked=[]
    for c,i,take in reversed(decisions):
        if capacity>=c and take[capacity-c]:
            picked.append(i);capacity-=c
    return result+picked[::-1]

def link(q,archive,record,frames,reader,zero,flow,has):
    revision=flow.native.api.pilot.RAW[1]
    tr=flow.native.adapt_isetrace_record(flow.native.parse_isetrace_record(archive),source_revision=revision)
    events=tr.events
    rebuilt,refs,ordinals,_=flow.extract(events,has)
    assert len(rebuilt)==len(refs)==len(frames)
    counters=Counter()
    for seq,reference,(delta,flags) in zip(rebuilt,refs,frames):
        assert Counter(seq)==Counter(map(tuple,delta))
        flags_from_ref={}
        for (src,tgt),n in reference.items():
            assert n>0
            flags_from_ref[src]=flags_from_ref.get(src,0)|1
            flags_from_ref[tgt]=flags_from_ref.get(tgt,0)|2
        assert [[a,k] for a,k in sorted(flags_from_ref.items())]==flags
        counters["exact_sequence"]+=seq==list(map(tuple,delta))
        counters["delta_ops"]+=len(seq)
        counters["groups"]+=1
    origins={r[0]:r[1:] for r in reader.execute("select source,role,position,length,digest from origin where q=?",(q,))}
    producers=[[None,None,None,None] for _ in ordinals]
    lookup={};boundaries=[];pending=0;stage=1
    for event_idx,e in enumerate(events):
        if e.event_type not in {"tool_call","tool_output"}:continue
        idx=ordinals[e.call_id]
        is_output=e.event_type=="tool_output"
        pointer="/content" if is_output else "/raw_arguments"
        s=field(e,pointer)
        assert s not in lookup
        pos=e.position.message_index
        lookup[s]=(stage,e,pointer)
        slots=producers[idx]; k=0 if is_output else 2
        assert slots[k] is None
        slots[k:k+2]=[s,stage]
        pending+=-1 if is_output else 1
        assert pending>=0
        if not pending:
            boundaries.append((event_idx,pos));stage+=1
    assert pending==0 and len(boundaries)==len(frames)
    assert all(s is not None for row in producers for s in row)
    assert len(lookup)==len(ordinals)*2
    assert set(origins)<=set(lookup)
    sources={}
    for s,(role,pos,length,checksum) in origins.items():
        group,e,pointer=lookup[s];body=getattr(e,pointer[1:])
        assert (e.event_type,e.position.message_index,len(body),sha(body.encode()))==(role,pos,length,checksum)
        sources[s]=group
    spans=defaultdict(list)
    for j,s,lo,hi in reader.execute("select id,source,lo,hi from span where q=?",(q,)):
        assert 0<=lo<hi<=origins[s][2]
        spans[j].append((s,lo,hi))
    ranked=[]; available_at={}; rank_rows={}
    for i,c,u,node_hash in reader.execute("select id,tokens,utility,node_hash from node where q=? order by rank",(q,)):
        ranked.append((i,c,round(u*(1<<32))));rank_rows[i]=(c,node_hash)
        available_at[i]=max((sources[s] for s,_,_ in spans[i]),default=None)
    assert len(record["rr"])==len(ranked)
    for idx,r in enumerate(record["rr"]):
        assert rank_rows[idx]==(r["token_count"],sha(r["node_id"].encode()))
        candidate=[]
        for s in r["source_spans"]:
            f=sha(compact([s["event_id"],s["json_pointer"]]))
            assert f in origins
            candidate.append((f,s["char_start"],s["char_end"]))
        assert sorted(candidate)==sorted(spans[idx])
    counters.update(origins=len(origins),spans=sum(map(len,spans.values())),nodes=len(ranked),
                    orphan=sum(t is None for t in available_at.values()),producers=len(producers))
    before=Counter();steps=[]
    for step,((event_end,message_end),(delta,flags)) in enumerate(zip(boundaries,frames),1):
        change=Counter()
        for a,b,d in delta:
            assert producers[a][1]<=step and producers[b][1]<=step
            change[a]+=d
        writes=[]
        for a,gain in sorted(change.items()):
            if gain:
                n=before[a];before[a]+=gain;assert before[a]>=0
                writes.append([a,n,before[a]])
        assert set(k for k,n in before.items() if n)=={i for i,mask in flags if mask&1}
        active={i for i,s in available_at.items() if s is not None and s<=step}
        ids=select(ranked,active)
        steps.append([event_end,message_end,writes,ids])
    intended=zero.execute("select p.members from edge e join packet p on p.id=e.packet_id where e.q=? and e.source=? and e.start<=0 order by e.start desc limit 1",(q,min(origins))).fetchone()[0]
    assert steps[-1][3]==[i for i, in struct.iter_unpack("<H",intended)]
    return dict(producers=producers,sources=sorted(sources.items()),steps=steps),dict(counters)

def main():
    reg=read(D/"registration.json")
    assert digest(D/"PROTOCOL_RU.md")==reg["protocol"]
    manifests={}
    for name,path in (("r39",R39),("r44",R44),("flow",FLOW),("zero",R46)):
        assert digest(path/"manifest.json")==reg[name]
        manifests[name]=read(path/"manifest.json")["files"]
    def signed(name,path):
        assert digest(path)==manifests[name][path.name]
    for f in ("reader.sqlite","provenance.json","panel.json"):signed("r39",R39/f)
    for f in ("normalized.json.gz","fixture.py","fixture-seal.json"):signed("r44",R44/f)
    signed("flow",FLOW/"flow.py");signed("zero",R46/"view.sqlite")
    sys.path.insert(0,str(FLOW));import flow
    pilot=flow.native.api.pilot
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/"tokenizer.json")))
    def has(body):return bool(pilot.token_chunks(body,tokenizer=tok,max_tokens=504,overlap_tokens=64))
    fixture=R44/"normalized.json.gz"
    assert digest(fixture)==read(R44/"fixture-seal.json")["fixture"]
    plain=gzip.decompress(fixture.read_bytes());all_frames=json.loads(plain)
    assert len(all_frames)==1207 and 31279==sum(map(len,all_frames))
    meta=read(R39/"provenance.json")
    panel=read(R39/"panel.json")["queries"]
    traj_alias={x["trajectory"]:x["number"] for x in panel}
    query_alias={x["query"]:x["number"] for x in panel}
    raw_hash={r["query"]:r["raw_record_sha"] for r in meta["trajectory_checks"]}
    reader=db(R39/"reader.sqlite");zero=db(R46/"view.sqlite")
    assert {n:(qh,th) for n,qh,th in reader.execute("select * from query")}=={r["number"]:(r["query"],r["trajectory"]) for r in panel}
    naming={};offsets=[];cursor=1
    for j in range(8):
        p=FLOW/f"trace-{j}.json.gz";signed("flow",p)
        for name in read(p):
            assert name not in naming
            naming[name]=j
    ordered=sorted(naming,key=lambda t:hashlib.sha256(("sql-flow-v1/"+t).encode()).digest())
    assert len(ordered)==len(all_frames)
    for frame in all_frames:
        raw=compact(frame)
        assert plain[cursor:cursor+len(raw)]==raw
        offsets.append([cursor,cursor+len(raw),sha(raw)])
        cursor+=len(raw)+1
    assert plain[cursor-1:]==b"]\n"
    located={name:(traj_alias[sha(name.encode())],i) for i,name in enumerate(ordered) if sha(name.encode()) in traj_alias}
    assert len(located)==40
    audit={};queries={};pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"')
    for j in range(8):
        f=flow.native.api.TR/f"forecasts-main-{j}.json.gz"
        assert digest(f)==meta["candidate_shards"][f.name]
        records={r["t"]:r for r in read(f) if sha(r["q"].encode()) in query_alias}
        path=flow.native.api.RAW/f"trajectories-{j:05d}.jsonl"
        signed("flow",FLOW/f"shard-{j}.json")
        h=hashlib.sha256()
        with path.open("rb") as inp:
            for raw in inp:
                h.update(raw);m=pattern.search(raw)
                if not m:continue
                name=m[1].decode()
                if name not in records:continue
                q,slot=located[name]
                assert q==query_alias[sha(records[name]["q"].encode())] and naming[name]==j
                assert sha(raw)==raw_hash[q] and q not in queries
                obj=json.loads(raw);assert obj["session_id"]==name
                queries[q],counts=link(q,obj,records[name],all_frames[slot],reader,zero,flow,has)
                audit[q]=dict(slot=slot,fixture_span=offsets[slot],raw_record=sha(raw),counts=counts)
        assert h.hexdigest()==meta["raw_shards"][path.name]==read(FLOW/f"shard-{j}.json")["source"]
        print("shard",j,"joined",len(queries),flush=True)
    assert set(queries)==set(query_alias.values())
    save("projection.json.gz",dict(version=1,queries=queries))
    save("links.json",dict(fixture=digest(fixture),fixture_uncompressed=sha(plain),reader=digest(R39/"reader.sqlite"),queries=audit))
    reader.close();zero.close()

if __name__=="__main__":
    if os.environ.get("PYTHONHASHSEED")=="48017":
        main()
    else:
        subprocess.run([sys.executable,"-B",__file__],env=dict(os.environ,PYTHONHASHSEED="48017"),check=True)
