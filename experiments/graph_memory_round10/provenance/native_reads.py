"""Exercise the real MemTrace components on one isolated archived history per direction."""
from common import *
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import base64,os,sqlite3,sys,tempfile,time,zipfile
import SMOKE as api
from memtrace.contracts import FactType
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore
from memtrace.semantic_memory import SemanticStore
from memtrace.recall import RecallService
sys.path.insert(0,str(R9/"budget"));import sketch
OUT=ROOT/"native"
def decoded(render):
    lines=render.splitlines()
    return json.loads("\n".join(lines[2:-1]))
def extract(res,k,old,typ):
    doc=decoded(res["rendered"])
    facts=[]
    if "sections" in doc:
        for section in doc["sections"]:
            if not section.get("content_complete"):continue
            for event in section.get("content",{}).get("events",[]):
                if event["revision_id"]!=old:continue
                facts.extend(event.get("facts",[]))
    else:
        for name in ["restored_code_changes","restored_tests_and_failures","supporting_context","restored_decisions"]:
            facts.extend(doc.get(name,[]))
    matches=[]
    for f in facts:
        key=f.get("key",{})
        if (key.get("canonical_entity_id"),key.get("evidence_type"),key.get("revision_constraint"))==(
            k.canonical_entity_id,k.evidence_type.value,"revision:"+old):
            c=f.get("content")
            if isinstance(c,dict) and c.get("record_kind")==typ:matches.append(c)
    return matches[0] if len(matches)==1 else None
def receipt(series,rev,obs,status):
    return dict(record_kind="executed_pytest_node",nodeid=obs["node"],success=status=="passed",
                execution_revision=rev,source_receipt=obs["source_ref"],scenario=series,
                basis="pytest node phase within a batch")
def frozen(r):
    return OUT/(sha(r["key"].encode())[:16]+".zip")
def native_log(r,stage):
    return OUT/(sha(r["key"].encode())[:16]+"-"+stage+".gz")
def directory_bytes(wd):
    return sum(f.stat().st_size for f in wd.rglob("*") if f.is_file())
def snapshot(wd,p):
    with zipfile.ZipFile(p,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(wd.rglob("*")):
            if f.is_file():z.write(f,f.relative_to(wd).as_posix())
def label(o):
    return ("passed" if o["success"] else "failed") if o and isinstance(o.get("success"),bool) else None
def first(r):
    answers=[];raws=[];packets={};directory={};t=time.monotonic()
    nodes=[o["node"] for o in r["items"]];old,new=r["old"],r["new"]; repo="sympy/sympy"
    with tempfile.TemporaryDirectory(prefix="r10-native-") as temp:
        wd=Path(temp);db,sem,ps,svc,mid=api.open_store(wd,repo,old)
        for j,o in enumerate(r["items"]):
            k=api.key(o["node"],old)
            directory[o["node"]]=api.write(ps,mid,"old"+str(j),k,receipt(r["key"],old,o,o["prior"]),old)
        cost_test_only=directory_bytes(wd)
        for mode,pkt in r["packets"].items():
            keyname="suite-observation/"+mode
            k=api.key(keyname,old,FactType.CODE_OBSERVATION)
            content=dict(record_kind="dependency_sketch",source_revision=old,format=mode,node_order_sha=sha(packed(nodes)),
                         original_bytes=pkt["bytes"],sha256=pkt["sha256"],data=pkt["data"])
            directory[keyname]=api.write(ps,mid,mode,k,content,old)
        for j,o in enumerate(r["items"]):
            node=o["node"];k=api.key(node,old)
            res=api.request(svc,mid,repo,"before"+str(j),k,old)
            obs=extract(res,k,old,"executed_pytest_node")
            checked=obs is not None and obs["nodeid"]==node and obs["execution_revision"]==old and obs["source_receipt"]==o["source_ref"]
            answers.append(dict(node=node,before=label(obs) if checked else None,before_state=res["state"]))
            raws.append(dict(query="old_exact",node=node,**res))
        invalidate=sem.advance_workspace_revision(run_id="run-1",branch_id="main",new_revision_id=new,source_event_id="changed",
                      changed_entities=tuple(sorted({"file:"+s.split("|",1)[0] for s in r["changed"]})))
        for mode in r["packets"]:
            name="suite-observation/"+mode;k=api.key(name,old,FactType.CODE_OBSERVATION)
            res=api.request(svc,mid,repo,"packet-"+mode,k,new,directory[name])
            got=extract(res,k,old,"dependency_sketch")
            valid=False
            if got and got.get("node_order_sha")==sha(packed(nodes)):
                data=base64.b64decode(got["data"])
                valid=len(data)==256*len(nodes) and sha(data)==got["sha256"] and got["source_revision"]==old
            if valid:
                state=sketch.decoded(data,len(nodes))
                packets[mode]=[bool(sketch.has(state,j,r["changed"],0)) for j in range(len(nodes))]
            else:packets[mode]=None
            raws.append(dict(query="sketch_"+mode,node=None,decoded=valid,**res))
        for j,o in enumerate(r["items"]):
            n=o["node"];k=api.key(n,old)
            res=api.request(svc,mid,repo,"history"+str(j),k,new,directory[n]);doc=decoded(res["rendered"])
            obs=extract(res,k,old,"executed_pytest_node")
            valid=bool(obs and obs["nodeid"]==n and obs["execution_revision"]==old and obs["source_receipt"]==o["source_ref"])
            answers[j].update(historical=label(obs) if valid else None,historical_state=res["state"],
                              marked_historical=bool(doc.get("historical_sources_may_not_be_current_code_truth")))
            raws.append(dict(query="old_from_new",node=n,**res));k=api.key(n,new)
            res=api.request(svc,mid,repo,"cur"+str(j),k,new)
            obs=extract(res,k,new,"executed_pytest_node")
            answers[j].update(current_before=label(obs),current_before_state=res["state"])
            raws.append(dict(query="new_before_run",node=n,**res))
        ps.close();db.close()
        total=directory_bytes(wd);snapshot(wd,frozen(r))
    put(native_log(r,"history"),raws)
    return dict(key=r["key"],answers=answers,packets=packets,milestone=mid,invalidated=invalidate,
                bytes_at_test_checkpoint_including_wal=cost_test_only,closed_archive_logical_bytes=total,
                zip_size=frozen(r).stat().st_size,native_snapshot_sha=fh(frozen(r)),elapsed=time.monotonic()-t)
def current(args):
    r,pr,future=args
    assert pr["native_snapshot_sha"]==fh(frozen(r))
    out=[];raws=[];rev=r["new"];mid=pr["milestone"]
    with tempfile.TemporaryDirectory(prefix="r10-confirm-") as temp:
        wd=Path(temp)
        with zipfile.ZipFile(frozen(r)) as z:z.extractall(wd)
        db=StateDatabase(wd/"state.sqlite");sem=SemanticStore(db)
        ps=PageStore(wd/"pages",db,"run-1","main",projector=sem.project_page)
        svc=RecallService(semantic_index=sem,page_reader=ps)
        for i,o in enumerate(r["items"]):
            n=o["node"];actual=future[n]["status"]
            if actual not in ("passed","failed"):
                out.append(dict(node=n,status=None,state="TEST_UNRESOLVED"));continue
            k=api.key(n,rev)
            item=dict(node=n,source_ref=future[n]["source_ref"])
            api.write(ps,mid,"new"+str(i),k,receipt(r["key"],rev,item,actual),rev)
            res=api.request(svc,mid,"sympy/sympy","now"+str(i),k,rev)
            got=extract(res,k,rev,"executed_pytest_node")
            valid=bool(got and got['nodeid']==n and got['source_receipt']==item['source_ref'] and got['execution_revision']==rev)
            out.append(dict(node=n,state=res["state"],status=label(got) if valid else None))
            raws.append(dict(query="new_after_run",node=n,**res))
        ps.close();db.close()
    put(native_log(r,"current"),raws)
    return dict(key=r["key"],receipts=out)
def main():
    OUT.mkdir(exist_ok=True)
    records=get(ROOT/"inputs.gz");lock=get(ROOT/"input-lock.json")
    assert lock["inputs"]==fh(ROOT/"inputs.gz")
    if sys.argv[1]=="first":
        with ProcessPoolExecutor(5) as ex:out=list(ex.map(first,records))
        put(ROOT/"history.gz",out)
        print("native",len(out),Counter((k,v is not None) for r in out for k,v in r['packets'].items()),flush=True)
    elif sys.argv[1]=="current":
        plan=get(ROOT/"plan-lock.json");assert plan["plans"]==fh(ROOT/"plans.gz")
        data=get(ROOT/"fresh-results.gz");past={r["key"]:r for r in get(ROOT/"history.gz")}
        with ProcessPoolExecutor(5) as ex:out=list(ex.map(current,[(r,past[r["key"]],data[r["key"]]) for r in records]))
        put(ROOT/"current.gz",out)
        print(len(out),"reopened stores",flush=True)
if __name__=="__main__":main()
