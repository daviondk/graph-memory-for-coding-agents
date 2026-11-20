"""Secondary adaptive-flat control using the genuine historic packet endpoint and locked test receipts."""
from common import *
import base64, tempfile
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor

@lru_cache(maxsize=2)
def graphs(panel):
    return {(g["task"],g["direction"]):g for g in get(PANELS[panel]/"graphs.json.gz")}

def exercise(r):
    import native_reads as native, SMOKE as api, sketch
    from memtrace.contracts import FactType
    nodes=[o["node"] for o in r["items"]]
    g=graphs(r["panel"])[r["task"],r["direction"]];edges=g["edges"]
    sets=[set(edges.get("shared",[]))|set(edges.get(n,[])) for n in nodes]
    layout=sketch.layout(sets,len(nodes)*256)
    encoded=sketch.encoded(layout["adaptive_flat"],0)
    assert sha(sketch.encoded(layout["selected"],0))==r["packets"]["selected"]["sha256"]
    mode="adaptive_flat";name="suite-observation/"+mode
    k=api.key(name,r["old"],FactType.CODE_OBSERVATION)
    with tempfile.TemporaryDirectory(prefix="r10-native-adaptive-") as temp:
        db,sem,ps,svc,mid=api.open_store(Path(temp),"sympy/sympy",r["old"])
        content=dict(record_kind="dependency_sketch",source_revision=r["old"],format=mode,node_order_sha=sha(packed(nodes)),
                     original_bytes=len(encoded),sha256=sha(encoded),data=base64.b64encode(encoded).decode())
        page=api.write(ps,mid,mode,k,content,r["old"])
        sem.advance_workspace_revision(run_id="run-1",branch_id="main",new_revision_id=r["new"],source_event_id="changed",
                                      changed_entities=tuple(sorted({"file:"+s.split("|",1)[0] for s in r["changed"]})))
        ans=api.request(svc,mid,"sympy/sympy","packet-"+mode,k,r["new"],page)
        restored=native.extract(ans,k,r["old"],"dependency_sketch");assert restored==content
        payload=base64.b64decode(restored["data"]);assert len(payload)==len(nodes)*256
        bits=[bool(sketch.has(sketch.decoded(payload,len(nodes)),i,r["changed"],0)) for i in range(len(nodes))]
        assert all(bit or not exact for bit,exact in zip(bits,r["expected_impact"]))
        ps.close();db.close()
    return dict(key=r["key"],positive=bits,receipt=ans,page=page,raw_bytes=len(payload))

def forecast():
    inputdata=get(ROOT/"inputs.gz")
    past={x["key"]:x for x in get(ROOT/"history.gz")}
    with ProcessPoolExecutor(4) as ex:responses=list(ex.map(exercise,inputdata))
    allrows=[]
    for r,out in zip(inputdata,responses):
        k=r["key"];items=past[k]["answers"];pos=out["positive"]
        nodes=[x["node"] for x in items];assert nodes==[x["node"] for x in r["items"]]
        order=sorted(range(len(nodes)),key=lambda i:(not pos[i],items[i]["historical"]!="failed",
                     sha(packed([r["task"],r["direction"],nodes[i],"r10-priority"]))))
        pay=set(order[:len(nodes)//3])
        for idx,node in enumerate(nodes):
            src="confirm" if idx in pay else ("abstain" if pos[idx] else "historical_prediction")
            allrows.append(dict(key=k,node=node,policy="adaptive_flat",source=src,historical=items[idx]["historical"] if src=="historical_prediction" else None))
    put(ROOT/"adaptive-native.gz",responses);put(ROOT/"adaptive-plans.gz",allrows)
    put(ROOT/"adaptive-plan-lock.json",{n:fh(ROOT/n) for n in ("adaptive.py","POSTHOC.md","inputs.gz","history.gz","adaptive-plans.gz","adaptive-native.gz")})

def score():
    from score import contrast,stats
    lock=get(ROOT/"adaptive-plan-lock.json")
    for n,h in lock.items():assert fh(ROOT/n)==h
    baseline=[r for r in get(ROOT/"outcomes.gz") if r["policy"]=="selected"]
    idx={(r["key"],r["node"]):r for r in baseline}
    fresh={r["key"]:{x["node"]:x["status"] for x in r["receipts"]} for r in get(ROOT/"current.gz")}
    new=[]
    for row in get(ROOT/"adaptive-plans.gz"):
        k,n,s=row["key"],row["node"],row["source"];ref=idx[k,n]
        ans=fresh[k][n] if s=="confirm" else row["historical"]
        new.append({**row,"task":ref["task"],"panel":ref["panel"],"truth":ref["truth"],"answer":ans,"correct":ans==ref["truth"]})
    panels={}
    for panel in ["both","primary","holdout"]:
        block=[r for r in new+baseline if panel=="both" or r["panel"]==panel]
        panels[panel]=dict(adaptive_flat=stats([r for r in block if r["policy"]=="adaptive_flat"]),selected_minus_adaptive=contrast(block,"selected","adaptive_flat"))
    put(ROOT/"adaptive-outcomes.gz",new);put(ROOT/"adaptive-results.json",panels);print(json.dumps(panels))

if __name__=="__main__":
    if sys.argv[1]=="forecast":forecast()
    elif sys.argv[1]=="score":score()
