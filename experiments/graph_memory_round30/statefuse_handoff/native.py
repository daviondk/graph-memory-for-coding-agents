"""Exercise native StateFuse with two worker replicas, correction and late replay."""
import gzip,json,sys
from collections import defaultdict
from statistics import mean,median
from source import CACHE,HERE,REV,sha
sys.path.insert(0,str(CACHE/"src"))
from statefuse import Memory,merge,materialize
LABELS=CACHE.parents[1]/"x20-r28-retraction/stale-projection/evaluator/labels.json.gz"
def wire(obj):return json.dumps(obj,separators=(",",":"),ensure_ascii=False,sort_keys=True).encode()
def projection(state):
    return tuple(sorted((c.value,state.evidence_by_id[c.evidence_ids[0]].pointer) for cs in state.active_claims_by_key.values() for c in cs))
def case(row):
    logs=[];atoms=[]
    for side in ("old","new"):
        ref=row[side+"_source"];value=row[side];m=Memory(replica_id="worker-"+side)
        s=m.add_source(source_type="tool_result",message_id=ref);e=m.add_evidence(pointer=ref,content=value,source_id=s)
        claim=m.add_claim(namespace="history",subject=row["case"],predicate="state",value=value,confidence=1.0,evidence_ids=[e])
        logs.append(m.load_oplog());atoms.append((claim,e,value,ref))
    a,b=logs;target=tuple(sorted((v,r) for _,_,v,r in atoms))
    original=merge(a,b);left=materialize(original);full=projection(left)
    right=projection(materialize(merge(b,a)));duplicate=projection(materialize(merge(original,a)))
    m=Memory(replica_id="coordinator");m.merge_from(original)
    old_id=atoms[0][0];new_ev=atoms[1][1];old_ref=left.claim_refs_by_id[old_id]
    m.retract_claim(target_claim_ref=old_ref,evidence_ids=[new_ev],reason="superseded in current view")
    after=projection(m.materialize());replay=projection(materialize(merge(m.load_oplog(),a)))
    expected=(atoms[1][2:],)
    def register(observations,withdrawn):
        active={cid:(v,r) for cid,e,v,r in observations if cid not in withdrawn}
        return tuple(sorted(active.values()))
    flat=register(atoms,());flat_after=register(atoms+atoms[:1],{old_id})
    lww=(atoms[1][2:],)
    return {"native_both":full==target,"flat_both":flat==target,"last_both":lww==target,
            "same_projection":full==flat,"native_latest":after==expected,"flat_latest":flat_after==expected,"last_latest":lww==expected,
            "merge_commutes":full==right,"repeat_stable":full==duplicate,"late_replay_stable":after==replay,
            "conflict_present":bool(left.conflicts),"facts_equal":row["old"]==row["new"],
            "same_source":row["old_source"]==row["new_source"],"native_ops":len(original.op_ids()),
            "native_log_bytes":len(wire([op.to_dict() for op in original.iter_ops()])),
            "projection_bytes":len(wire(full)),"compressed_log_bytes":len(gzip.compress(wire([op.to_dict() for op in original.iter_ops()]),mtime=0))}
def main():
    src=json.loads((HERE/"source-lock.json").read_bytes())
    assert all(sha(CACHE/n)==h for n,h in src["files"].items())
    parent=HERE.parents[1]/"graph_memory_round28/retraction_sources/blind-seal.json"
    assert sha(LABELS)==json.loads(parent.read_bytes())["labels_sha"]
    rows=json.loads(gzip.decompress(LABELS.read_bytes()));grouped={}
    for row in rows:
        q=row["case"]
        if q in grouped:assert all(grouped[q][k]==row[k] for k in ("old","new","old_source","new_source"))
        grouped[q]=row
    assert len(grouped)==400
    lock={"protocol":sha(HERE/"PROTOCOL_RU.md"),"script":sha(HERE/"native.py"),"code":sha(HERE/"source-lock.json"),"inputs":sha(LABELS),"n":len(grouped)}
    (HERE/"input-lock.json").write_bytes(wire(lock))
    result={q:case(r) for q,r in sorted(grouped.items())};out=HERE/"outcomes.json.gz"
    out.write_bytes(gzip.compress(wire(result),mtime=0))
    first=next(iter(result.values()));sums={k:sum(r[k] for r in result.values()) for k,v in first.items() if isinstance(v,bool)}
    quant={k:{"mean":mean(r[k] for r in result.values()),"median":median(r[k] for r in result.values())} for k,v in first.items() if type(v)==int}
    (HERE/"results.json").write_bytes(wire({"n":len(result),"counts":sums,"resources":quant,"outcomes":sha(out)}))
if __name__=="__main__":main()
