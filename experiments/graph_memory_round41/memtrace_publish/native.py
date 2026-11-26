"""Run the released MemTrace store, page writer, and complete RecallService on synthetic boundary cases."""
import argparse
import dataclasses
import gzip
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

from certificate import canonical,digest,exhaustive,transfer
from synthetic import POSITIVE,NEGATIVE,fixture

D=Path(__file__).resolve().parent
REV="5508f8be81025d8aa90726b1e06aef4ea484e577"
SRC=Path("/mnt/d/CodexResearch/x20-r40-memtrace-runtime")/REV/"src"
sys.path.insert(0,str(SRC))
from memtrace.contracts import (Authority,Event,EventGroup,EvidenceDraft,EvidenceKey,FactType,
                                MilestoneSpec,PlanSpec,RecallIntent)
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore
from memtrace.planning import PlanRegistry
from memtrace.recall import RecallService
from memtrace.semantic_memory import SemanticStore

STAMP="2000-01-01T00:00:00Z"
MODES=("native_only","derived_bound","certified","asserted_certified","unchecked")


def evidence(revision):
    return EvidenceKey(FactType.CODE_OBSERVATION,"file:sample","read_block","revision:"+revision,"main")


def write(pages,mid,revision,event_id,content,authority,bind_event=True):
    key=evidence(revision)
    event=Event(event_id,"CODE_OBSERVED",{},(EvidenceDraft(key,content,authority),),
                (key.canonical_entity_id,),mid if bind_event else None,"observe",revision,STAMP)
    group=EventGroup("g_"+event_id,"ACTION","run","main",revision,(event,),mid,created_at=STAMP)
    manifest=pages.append_group(group) or pages.checkpoint("USER_CHECKPOINT")
    assert manifest and len(pages.last_sealed)==1
    return pages.last_sealed[0].page_id


def ask(sem,pages,mid,revision,call):
    key=evidence(revision)
    intent=RecallIntent(call,"repo","run","main",revision,(key,),mid,"Return the observed byte interval",
                        entity_refs=(key.canonical_entity_id,),max_pages=1,max_tokens=8192,
                        max_slice_tokens=8192,max_page_bytes_read=131072,max_blob_bytes_read=131072)
    answer=RecallService(semantic_index=sem,page_reader=pages).fault(intent)
    block=answer.block
    doc=json.loads("\n".join(block.rendered_content.splitlines()[2:-1]))
    match=[f for f in doc.get("restored_code_changes",[]) if f.get("key",{}).get("canonical_entity_id")=="file:sample"
           and f["key"].get("semantic_role")=="read_block" and f["key"].get("revision_constraint")=="revision:"+revision]
    assert len(match)<=1
    state=block.coverage.state.value
    assert (state=="COMPLETE")==bool(match)
    if match:
        assert key.key_digest in block.coverage.covered_keys and doc["temporal_semantics"]["source_revision_state"]=="CURRENT"
    return dict(state=state,record=match[0].get("content") if match else None,
                authority=match[0].get("authority") if match else None,temporal=doc.get("temporal_semantics"),
                rendered_sha256=digest(block.rendered_content.encode()),read_pages=len(answer.trace.pages_read),
                page_bytes=answer.trace.page_bytes_read,blob_bytes=answer.trace.blob_bytes_read,
                recovered_tokens=block.token_count,raw=block.rendered_content)


def native_case(root,mode,fixture):
    db=StateDatabase(root/"db.sqlite");sem=SemanticStore(db)
    app=PlanRegistry(db,sem).initialize_task(repository_id="repo",run_id="run",branch_id="main",revision_id="old",
        user_request="read a synthetic interval",plan=PlanSpec("read",(
            MilestoneSpec("M001","read","observe",("done",),("test",)),)),source_event_id="plan")
    mid=app.current_milestone_id
    pages=PageStore(root/"pages",db,"run","main",projector=sem.project_page)
    record=dict(body=fixture["observed"].decode("ascii"),read_receipt=fixture["read"],record_kind="initial_read")
    old_page=write(pages,mid,"old","source-observation",record,Authority.ASSERTED)
    before=ask(sem,pages,mid,"old","initial")
    assert before["state"]=="COMPLETE" and before["record"]==record
    n=sem.advance_workspace_revision(run_id="run",branch_id="main",new_revision_id="new",source_event_id="edit",
                                     changed_entities=("file:sample",))
    assert n==1
    # Inputs come from the genuine recovered source block and the trusted event; no new file bytes are available.
    observed=before["record"]["body"].encode("ascii")
    read=before["record"]["read_receipt"]
    status,cert=transfer(observed,read,fixture["edit"],fixture["target"])
    published=None
    if mode in ("certified","derived_bound","asserted_certified") and cert:
        published=cert
    elif mode=="unchecked":
        published=dict(body=observed.decode("ascii"),record_kind="unconditional_reissue")
    new_page=None
    if published:
        try:
            new_page=write(pages,mid,"new","publication",published,
                Authority.ASSERTED if mode=="asserted_certified" else Authority.DERIVED,
                bind_event=mode in ("derived_bound","asserted_certified"))
        except ValueError as exc:
            if mode!="derived_bound" or str(exc)!="DERIVED is not allowed for SUPPORTS":raise
            # Projection rolled back in the upstream SQLite transaction. Capture the actual evidence state.
            kept=db.connection.execute("SELECT count(*) FROM v2_semantic_evidence WHERE revision_id='new' AND evidence_type='CODE_OBSERVATION'").fetchone()[0]
            assert kept==0
            db.close()
            return dict(cert_decision=status,rejected=str(exc),new_sql_units=kept,invalidated=n),[before["raw"]]

    after=ask(sem,pages,mid,"new","current")
    assert after["record"]==published
    pages.close();db.close()
    # Replay after actual close/reopen of both upstream stores.
    db=StateDatabase(root/"db.sqlite");sem=SemanticStore(db)
    pages=PageStore(root/"pages",db,"run","main",projector=sem.project_page)
    reopened=ask(sem,pages,mid,"new","reopened")
    assert (after["state"],after["record"],after["authority"],after["temporal"])==(
             reopened["state"],reopened["record"],reopened["authority"],reopened["temporal"])
    pages.close();db.close()
    raw=[before.pop("raw"),after.pop("raw"),reopened.pop("raw")]
    result=dict(cert_decision=status, result=after, reopened=reopened, before=before, old_page=old_page,
                new_page=new_page, invalidated=n,checked_bytes=len(observed) if cert else 0)
    return result,raw


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    t=time.perf_counter();records={};raw={}
    assert digest((D/"PROTOCOL_RU.md").read_bytes())=="52a34496201bfa3f57dadfbffb1ec56dd0a9c9bef22563ccf680eb8c5b834863"
    for name in (["after"] if args.smoke else sorted(POSITIVE+NEGATIVE)):
        for size in ((48,) if args.smoke else (48,128)):
            f=fixture(name,size)
            for mode in MODES:
                key=f"{name}/{size}/{mode}";start=time.perf_counter()
                with tempfile.TemporaryDirectory(prefix="x20-memtrace-r41-") as td:
                    r,raw[key]=native_case(Path(td),mode,f)
                r["elapsed_s"]=time.perf_counter()-start
                records[key]=r
                if args.smoke:print(key,r["rejected"] if "rejected" in r else r["result"]["state"],flush=True)
    if args.smoke:return
    def save(name,val):
        data=canonical(val)+b"\n"
        (D/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)
    save("native-output.json.gz",records);save("rendered-blocks.json.gz",raw)
    save("run.json",dict(conditions=len(records),requests=sum(len(v) for v in raw.values()),sqlite=sqlite3.sqlite_version,
        python=sys.version,upstream=REV,lemma=exhaustive(),elapsed_s=time.perf_counter()-t,
        program={name:digest((D/name).read_bytes()) for name in ("PROTOCOL_RU.md","CONTRACT_ADDENDUM_RU.md","native.py","certificate.py","synthetic.py")},
        outputs={name:digest((D/name).read_bytes()) for name in ("native-output.json.gz","rendered-blocks.json.gz")}))
    print("Sealed",len(records),"condition runs and",sum(map(len,raw.values())),"actual recoveries.",flush=True)


if __name__=="__main__":main()

