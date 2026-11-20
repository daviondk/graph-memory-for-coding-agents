"""Only fictional fixtures, to determine the pinned public return envelope before decisions."""
import sys,json,tempfile,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UP=ROOT.parents[1]/"graph_memory_round6/published"
sys.path[:0]=[str(UP/"MemTrace/src"),str(UP/".linux-deps"),str(UP)]
import native
from memtrace.contracts import *
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore
from memtrace.semantic_memory import SemanticStore
from memtrace.planning import PlanRegistry
from memtrace.recall import RecallService
from hashlib import sha256
def key(node,revision,fact=FactType.TEST_RESULT):
    return EvidenceKey(fact,"test:"+node,"witness","revision:"+revision,"main","CURRENT")
def write(store,mid,eid,k,payload,rev):
    stamp="2000-01-01T00:00:00Z"
    event=Event("e"+eid,"TEST_EXECUTED" if k.evidence_type==FactType.TEST_RESULT else "CODE_OBSERVED",{},(EvidenceDraft(k,payload),),(k.canonical_entity_id,),mid,"observe",rev,stamp)
    group=EventGroup("g"+eid,"ACTION","run-1","main",rev,(event,),mid,created_at=stamp)
    manifest=store.append_group(group) or store.checkpoint("USER_CHECKPOINT"); assert manifest
    assert len(store.last_sealed)==1
    return store.last_sealed[0].page_id
def request(svc,mid,repo,call,k,rev,page=None):
    options=dict(max_pages=1,max_tokens=8192,max_slice_tokens=8192,max_page_bytes_read=131072,max_blob_bytes_read=131072)
    if page:options.update(direct_page_ids=(page,),source_memory_ref="memoryref_"+sha256(page.encode()).hexdigest()[:24],temporal_scope=RecallTemporalScope.HISTORICAL_EXECUTION,require_exact_revision=False)
    intent=RecallIntent(recall_id=call,repository_id=repo,run_id="run-1",branch_id="main",revision_id=rev,
        required_evidence=() if page else (k,),current_milestone_id=mid,question="Return the registered receipt for "+k.canonical_entity_id,
        entity_refs=(k.canonical_entity_id,),**options)
    res=svc.fault(intent)
    return dict(state=res.block.coverage.state.value,rendered=res.block.rendered_content,pages=len(res.trace.pages_read),
                page_bytes=res.trace.page_bytes_read,blob_bytes=res.trace.blob_bytes_read,tokens=res.block.token_count)
def open_store(path,repo,old):
    db=StateDatabase(path/"state.sqlite");sem=SemanticStore(db);reg=PlanRegistry(db,sem)
    plan=PlanSpec("Read a test outcome",(MilestoneSpec("m1","Inspect","Retrieve observed test receipts",("Outcome available",),("Read a receipt",)),))
    head=reg.initialize_task(repository_id=repo,run_id="run-1",branch_id="main",revision_id=old,user_request="Retrieve previous test outcomes",plan=plan,source_event_id="plan")
    ps=PageStore(path/"pages",db,"run-1","main",projector=sem.project_page)
    return db,sem,ps,RecallService(semantic_index=sem,page_reader=ps),head.current_milestone_id
def main():
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        db,sem,ps,svc,mid=open_store(Path(temp),"example/repo","old")
        k=key("foo::bar","old")
        p=write(ps,mid,"01",k,{"nodeid":"foo::bar","command":"pytest foo::bar","success":False,"record_kind":"observed","marker":"unique_friendly_smoke","stamp":"old"},'old')
        x={"before":request(svc,mid,"example/repo","before",k,"old")}
        x["transition"]=sem.advance_workspace_revision(run_id="run-1",branch_id="main",new_revision_id="new",source_event_id="changed",changed_entities=("file:a.py",))
        x["historical"]=request(svc,mid,"example/repo","history",k,"new",p)
        x["current"]=request(svc,mid,"example/repo","current",key("foo::bar","new"),"new")
        x["keyed_old_after"]=request(svc,mid,"example/repo","before2",k,"old")
        ps.close();db.close()
        (ROOT/"smoke-receipts.json").write_text(json.dumps(x,indent=2),encoding="utf8")
        for n,r in x.items():print(n,(r['state'],r['pages'],len(r['rendered']),"unique_friendly_smoke" in r['rendered']) if isinstance(r,dict) else r)
if __name__=="__main__":main()
