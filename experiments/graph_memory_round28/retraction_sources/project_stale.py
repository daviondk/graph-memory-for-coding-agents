"""Build separable blind histories and single-query inputs, never crop using marked sources."""
from formats import *
from inspect_shapes import P
def opaque(*fields):return hashed("\0".join(["stale-blind-v1",*map(str,fields)]))[:24]
def main():
    assert sha(P/"stale.json")==PINS[P/"stale.json"]
    out=P/"stale-projection";history=out/"history";history.mkdir(parents=True,exist_ok=True);evaldir=out/"evaluator";evaldir.mkdir(exist_ok=True)
    qs=[];g=[];inventory={};n=0
    for r in json.loads((P/"stale.json").read_bytes()):
        uid=r["uid"];k=opaque("case",uid);sessions=[]
        for si,(session,ts) in enumerate(zip(r["haystack_session"],r["timestamps"],strict=True)):
            address=opaque("source",uid,si)
            turns=[dict(id=opaque("turn",uid,si,ti),role=t["role"],text=t["content"]) for ti,t in enumerate(session)]
            sessions.append(dict(id=address,sequence=si,time=ts,turns=turns));n+=len(turns)
        f=history/(k+".json.gz");inventory[k]=write(f,dict(case=k,sources=sessions))
        old,new=r["relevant_session_index"]
        for dim,q in sorted(r["probing_queries"].items()):
            qid=opaque("question",uid,dim)
            qs.append(dict(qid=qid,case=k,question=q))
            g.append(dict(qid=qid,case=k,uid=uid,dimension=dim,scenario_type=r["type"],old=r["M_old"],new=r["M_new"],old_source=sessions[old]["id"],new_source=sessions[new]["id"],rubric=r["explanation"]))
    qs.sort(key=lambda r:r["qid"]);g.sort(key=lambda r:r["qid"])
    assert len(qs)==len({x["qid"] for x in qs})==1200 and len(inventory)==400
    assert all(set(v)=={"qid","case","question"} for v in qs)
    write(out/"questions.json",qs);write(evaldir/"labels.json.gz",g)
    for k in inventory:
        r=json.loads(gzip.decompress((history/(k+".json.gz")).read_bytes()))
        assert set(r)=={"case","sources"} and len(r["sources"])==50
        assert all(set(e)=={"id","sequence","time","turns"} and all(set(t)=={"id","role","text"} for t in e["turns"]) for e in r["sources"])
    write(D/"blind-seal.json",dict(cases=len(inventory),questions=len(qs),source_sessions=50*len(inventory),turns=n,history=inventory,questions_sha=sha(out/"questions.json"),labels_sha=sha(evaldir/"labels.json.gz"),projector=sha(D/"project_stale.py"),source_sha=PINS[P/"stale.json"]))
    print("Verified 400 histories, 1200 separate questions,",n,"turns")
if __name__=="__main__":main()

