"""Join official candidate scores to timestamped source metadata and recorded support deltas."""
from collections import Counter,defaultdict
from pathlib import Path
import gzip,hashlib,json,math,re,sys
D=Path(__file__).resolve().parent
W=D.parents[1]
FLOW=W/"graph_memory_round44/flow_view"
SQLFLOW=FLOW.parent/"sql_flow"
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def load(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def save(path,value):
    data=(json.dumps(value,separators=(",",":"),sort_keys=True)+"\n").encode()
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)
def checked(path,manifest):
    assert digest(path.read_bytes())==manifest[path.name],path
    return load(path)
def main():
    assert digest((D/"PROTOCOL_RU.md").read_bytes())=="d3cf48c5ca195705b0abe4d721d41f72647235bad9fae18c146fdb84b9a030bd"
    sys.path.insert(0,str(FLOW));import flow
    known=load(FLOW/"manifest.json")["files"]
    frames=checked(SQLFLOW/"normalized.json.gz",load(SQLFLOW/"manifest.json")["files"])
    names=[name for j in range(8) for name in checked(FLOW/f"trace-{j}.json.gz",known)]
    ordered=sorted(names,key=lambda n:digest(("sql-flow-v1/"+n).encode()))
    assert len(ordered)==len(frames)==len(set(names))==1207
    by=dict(zip(ordered,frames))
    stamps=load(W/"graph_memory_round39/provenance_packet_demo/provenance.json")["candidate_shards"]
    shard_hash={};data={};joins=Counter()
    for j in range(8):
        candpath=flow.native.api.TR/f"forecasts-main-{j}.json.gz"
        groups=defaultdict(list)
        for r in checked(candpath,stamps):groups[r["t"]].append(r)
        file=flow.native.api.RAW/f"trajectories-{j:05d}.jsonl"
        h=hashlib.sha256();pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"')
        with file.open("rb") as inp:
            for raw in inp:
                h.update(raw);m=pattern.search(raw)
                if not m or m[1].decode() not in groups:continue
                name=m[1].decode();records=groups.pop(name)
                tr=flow.native.adapt_isetrace_record(flow.native.parse_isetrace_record(json.loads(raw)),source_revision=flow.native.api.pilot.RAW[1])
                sources={};ids={};pending=0;step=1
                for e in tr.events:
                    if e.event_type=="tool_call":
                        assert e.call_id not in ids;ids[e.call_id]=len(ids);pending+=1
                        sources[e.event_id,"/raw_arguments"]=(step,-1,len(e.raw_arguments))
                    elif e.event_type=="tool_output":
                        a=ids[e.call_id];pending-=1
                        sources[e.event_id,"/content"]=(step,a,len(e.content))
                        if not pending:step+=1
                assert not pending and len(by[name])==step-1
                deltas=[];bal=Counter()
                for delta,flags in by[name]:
                    changes=Counter()
                    for a,b,v in delta:changes[a]+=v
                    for a,v in changes.items():bal[a]+=v;assert bal[a]>=0
                    assert {a for a,b in bal.items() if b}=={a for a,k in flags if k&1}
                    deltas.append([[a,bal[a]] for a,v in sorted(changes.items()) if v])
                th=digest(name.encode())
                for r in records:
                    rows=[]
                    for index,c in enumerate(r["rr"]):
                        fields=c["source_spans"];assert fields
                        links=set();born=0
                        for f in fields:
                            b,a,length=sources[f["event_id"],f["json_pointer"]]
                            assert 0<=f["char_start"]<f["char_end"]<=length;born=max(born,b)
                            if a>=0:links.add(a)
                        cost=c["token_count"];s=float(c["score"])
                        assert cost>=0 and -1.00001<=s<=1.00001
                        rows.append((born,digest(c["node_id"].encode()),index,cost,round((1<<32)*math.exp(12*(s-.7))),sorted(links)))
                    # Sorting by the hash of the stable ID is independent of future candidates.
                    rows.sort();hash_q=digest(r["q"].encode());assert hash_q not in data
                    data[hash_q]=[th,[[b,i,c,v,a] for b,k,i,c,v,a in rows],deltas]
                    joins.update(candidates=len(rows),boundaries=len(deltas),multi=sum(len(t[-1])>1 for t in rows))
        assert not groups and h.hexdigest()==checked(FLOW/f"shard-{j}.json",known)["source"]
        shard_hash[file.name]=h.hexdigest();print("shard",j,len(data),flush=True)
    assert len(data)==2000 and len({v[0] for v in data.values()})==1207
    target=D/"input.json.gz";save(target,data)
    save(D/"input-seal.json",dict(protocol=digest((D/"PROTOCOL_RU.md").read_bytes()),file=digest(target.read_bytes()),
        candidate_shards=stamps,trace_shards=shard_hash,counters=dict(joins),flow=digest((SQLFLOW/"normalized.json.gz").read_bytes())))
if __name__=="__main__":main()
