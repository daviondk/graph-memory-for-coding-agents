"""Use only signed numeric FEEDS operations and producer birth stages, no raw tool arguments."""
from collections import Counter,defaultdict
from pathlib import Path
import gzip,hashlib,json,random

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
WORK=Path("D:/CodexResearch/x20-r53-churn")
def sha(data):return hashlib.sha256(data).hexdigest()
def encode(x):return json.dumps(x,sort_keys=True,separators=(",",":")).encode()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(n,v):
    data=encode(v)+b"\n"; (HERE/n).write_bytes(gzip.compress(data,mtime=0) if n.endswith(".gz") else data)
def sig(born,delta):
    # Hash the canonical atomic net, so harmless permutation within a transaction is idempotent.
    net=Counter()
    for a,b,d in delta:net[a,b]+=d
    return sha(encode([sorted(born),sorted([a,b,d] for (a,b),d in net.items() if d)]))
def extract():
    r48=EXP/"graph_memory_round48/observed_join";r44=EXP/"graph_memory_round44/sql_flow"
    src=r44/"normalized.json.gz";links=read(r48/"links.json");manifest=read(r48/"manifest.json")["files"]
    for f in ("projection.json.gz","links.json"):assert sha((r48/f).read_bytes())==manifest[f]
    assert links["fixture"]==sha(src.read_bytes())==read(r44/"fixture-seal.json")["fixture"]
    raw=gzip.decompress(src.read_bytes());assert sha(raw)==links["fixture_uncompressed"]
    old=read(r48/"projection.json.gz")["queries"];out={};c=Counter()
    for q,r in sorted(old.items()):
        start,stop,h=links["queries"][q]["fixture_span"];chunk=raw[start:stop];assert sha(chunk)==h
        frames=json.loads(chunk);assert len(frames)==len(r["steps"])
        born=defaultdict(list)
        for i,p in enumerate(r["producers"]):born[p[1]].append(i)
        all_events=[];weights=Counter();score=Counter();seen=set();ever=set();was_inactive=set()
        prev_winner=None
        for t,((d,flags),group) in enumerate(zip(frames,r["steps"]),1):
            net=Counter()
            for a,b,inc in d:net[a,b]+=inc
            changes=[[a,b,n] for (a,b),n in sorted(net.items()) if n]
            new=sorted(born[t]);seen.update(new)
            oldscore=dict(score);revoked=False
            for a,b,inc in changes:
                assert a in seen and b in seen
                oldw=weights[a,b];w=oldw+inc
                assert w>=0
                if inc<0:c["negative_edge_net"]+=1
                if oldw and not w:was_inactive.add((a,b));c["positive_to_zero"]+=1
                if not oldw and w and (a,b) in was_inactive:c["reactivations"]+=1
                if prev_winner is not None and a==prev_winner[0] and inc<0:revoked=True
                weights[a,b]=w;score[a]+=inc
            actual=sorted([i,oldscore.get(i,0),score[i]] for i in set(oldscore)|set(score) if oldscore.get(i,0)!=score[i])
            assert actual==group[2]
            assert {a for a,b in weights if weights[a,b]}=={a for a,k in flags if k&1}
            winner=min(seen,key=lambda i:(-score[i],i)) if seen else None
            outcome=None if winner is None else [winner,score[winner]]
            if revoked:c["frames_retract_from_winner"]+=1
            if prev_winner and outcome:
                c["winner_id_changes"]+=outcome[0]!=prev_winner[0]
                c["same_id_score_changes"]+=outcome[0]==prev_winner[0] and outcome[1]!=prev_winner[1]
                c["changed_winner_after_retract_from_winner"]+=revoked and outcome[0]!=prev_winner[0]
            prev_winner=outcome
            all_events.append({"t":t,"born":new,"delta":changes,"sha":sig(new,changes),"winner":outcome})
            c["input_delta_ops"]+=len(d);c["nonzero_edge_nets"]+=len(changes);c["frames"]+=1
            c["negative_source_revisions"]+=sum(after<before for _,before,after in actual)
        c["producers"]+=len(seen);out[q]=all_events
    save("workload.json.gz",out);save("registration.json",dict(stats=c,frames_sha=links["fixture"],projection_sha=manifest["projection.json.gz"],
        work_sha=sha((HERE/"workload.json.gz").read_bytes()),protocol_sha=sha((HERE/"PROTOCOL_RU.md").read_bytes()),source_sha=sha(Path(__file__).read_bytes())))
    print(dict(c))
def reads(n,q,t):
    rng=random.Random("r53|"+q+"|"+str(t))
    if n==0:return ()
    if n==1:return (rng.randrange(t),)
    return tuple(t if i%2==0 else rng.randrange(t) for i in range(8))
if __name__=="__main__":extract()

