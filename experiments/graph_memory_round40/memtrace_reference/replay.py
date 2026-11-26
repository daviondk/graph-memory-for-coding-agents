"""Native MemTrace projection on fixed, anonymized blocks. Does not load reference outcomes."""
import dataclasses
import hashlib
import importlib.util
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

from project import D, REV, digest, read, save

ROOT = Path("/mnt/d/CodexResearch/x20-r40-memtrace-runtime") / REV
sys.path.insert(0, str(ROOT / "src"))
from memtrace.contracts import (Event, EventGroup, EvidenceDraft, EvidenceKey, FactType,
                                MilestoneSpec, PlanSpec, RecallIntent)
from memtrace.database import StateDatabase
from memtrace.page_store import PageStore, TailReason
from memtrace.planning import PlanRegistry
from memtrace.recall.assembler import ContextAssembler
from memtrace.semantic_memory import SemanticStore


def run_case(tmp, blocks, changed_entities):
    db = StateDatabase(tmp / "revision.sqlite")
    try:
        sem = SemanticStore(db)
        app = PlanRegistry(db, sem).initialize_task(
            repository_id="repo", run_id="run", branch_id="main", revision_id="rev-old",
            user_request="read source", plan=PlanSpec("read source", (
                MilestoneSpec("M001", "Read", "edit", ("done",), ("test",)),)),
            source_event_id="plan-event")
        keys = [EvidenceKey(FactType.CODE_OBSERVATION, b["entity"], "READ_" + str(j),
                            "rev-old", "main") for j, b in enumerate(blocks)]
        assert keys and len(set(b["slot"] for b in blocks)) == len(keys)
        facts = tuple(EvidenceDraft(key, {"slot": b["slot"], "start": b["low"],
                     "end": b["high"], "length_bytes": b["bytes"]}) for key, b in zip(keys, blocks))
        pages = PageStore(tmp / "pages", db, "run", "main", projector=sem.project_page)
        pages.append_group(EventGroup(group_id="g", group_type="TOOL_RESULT", run_id="run",
            branch_id="main", revision_id="rev-old", milestone_id=app.current_milestone_id,
            events=(Event(event_id="e", event_type="TOOL_RESULT", payload={"observation":"opaque"},
                          facts=facts, entity_refs=tuple(dict.fromkeys(b["entity"] for b in blocks)),
                          milestone_id=app.current_milestone_id,revision_id="rev-old"),)))
        pages.checkpoint(TailReason.USER_CHECKPOINT)
        old = RecallIntent(recall_id="old", repository_id="repo", run_id="run", branch_id="main",
            revision_id="rev-old", required_evidence=tuple(keys), current_milestone_id=app.current_milestone_id,
            question="restore observed evidence")
        assert sem.locate_exact(old).complete
        closed = sem.advance_workspace_revision(run_id="run", branch_id="main",new_revision_id="rev-new",
                  source_event_id="file-change-event",changed_entities=changed_entities)
        rows = db.connection.execute("""SELECT evidence_id,canonical_entity_id,semantic_role,
            valid_to_revision,valid_to_cursor FROM v2_semantic_evidence
            WHERE evidence_type='CODE_OBSERVATION'""").fetchall()
        assert len(rows) == len(keys)
        cut, ids = [], set()
        for row in rows:
            j = int(row["semantic_role"].split("_")[1])
            assert row["canonical_entity_id"] == blocks[j]["entity"]
            if row["valid_to_cursor"] is None:
                assert row["valid_to_revision"] is None
            else:
                assert row["valid_to_revision"] == "rev-new"
                cut.append(j)
                ids.add(row["evidence_id"])
        assert {r[0] for r in db.connection.execute("""SELECT source_id FROM v2_semantic_edges
            WHERE edge_type='INVALIDATED_BY' AND target_id='file-change-event'""")} == ids
        assert len(cut) == closed
        missing = set(sem.locate_exact(old).missing_key_digests)
        assert missing == {keys[j].key_digest for j in cut}
        new = dataclasses.replace(old, recall_id="new", revision_id="rev-new")
        new_hits = len(sem.locate_exact(new).hits)
        temporal = ContextAssembler._revision_semantics(new, ("rev-old",))
        assert temporal["current_acceptance_requires_revalidation"]
        return dict(closed_slots=sorted(blocks[j]["slot"] for j in cut), blocks=len(keys),
                    closed_bytes=sum(blocks[j]["bytes"] for j in cut),
                    old_active=len(keys)-closed, new_intent_old_key_hits=new_hits,
                    edge_count=closed)
    finally:
        db.close()


def execute(blocks, changed):
    with tempfile.TemporaryDirectory(prefix="x20-memtrace-r40-") as td:
        return run_case(Path(td), blocks, tuple(changed))


def fixtures():
    path = ROOT / "tests/unit/test_core_harness_events.py"
    module = importlib.util.spec_from_file_location("authors_harness_tests", path)
    tests = importlib.util.module_from_spec(module)
    module.loader.exec_module(tests)
    tests_run = []
    for name in ("test_workspace_revision_advance_invalidates_old_current_evidence",
                 "test_revision_invalidation_is_selective_and_matches_symbols_to_changed_file"):
        with tempfile.TemporaryDirectory(prefix="x20-memtrace-fixture-") as td:
            getattr(tests, name)(Path(td))
        tests_run.append(name)
    blocks = [dict(slot=j,low=1,high=2,bytes=10,entity=entity) for j,entity in enumerate(
        ("symbol:a.py:one","symbol:a.py:two","file:other.py","file:a.py"))]
    symbol = execute(blocks, ("symbol:a.py:one",))
    file = execute(blocks, ("file:a.py",))
    assert symbol["closed_slots"] == [0] and file["closed_slots"] == [0,1,3]
    save("fixtures.json", dict(source_sha256=digest(path), python=sys.version, sqlite=sqlite3.sqlite_version,
         kernel=platform.release(), upstream=REV, tests_passed=tests_run, symbol=symbol,file=file))
    print("Passed original tests and independent exact symbol/file SQLite cases.", flush=True)


def main():
    fixtures()
    cases = read(D / "cases.json.gz")
    panel = read(D / "panel.json")
    predicate = {}
    for key, row in cases.items():
        changed = ("file:"+row["changed"],)
        predicate[key] = sorted(b["slot"] for b in row["chosen"]
                if SemanticStore._entity_affected("file:"+b["path"], changed))
    save("predicate.json.gz",predicate)
    result, times = {}, []
    t0 = time.perf_counter()
    for section in ("pilot","other"):
        for key in panel[section]:
            row = cases[key]
            start = time.perf_counter()
            blocks = [dict(b, entity="file:"+b["path"]) for b in row["chosen"]]
            current = execute(blocks, ("file:"+row["changed"],))
            times.append(time.perf_counter()-start)
            assert current["closed_slots"] == predicate[key]
            result[key] = current
            if len(result) % 250 == 0:
                print("SQL events",len(result),"total seconds",round(time.perf_counter()-t0,1),flush=True)
        if section == "pilot":
            median = statistics.median(times)
            free = min(shutil.disk_usage("/tmp").free,shutil.disk_usage(D).free)
            qualified = median < 0.5 and free > 100_000_000
            save("pilot-decision.json",dict(pilot_n=len(times), median_s=median,free_bytes=free,qualified=qualified))
            print("Pilot",len(result),"median",median,"extend",qualified,flush=True)
            if not qualified:
                break
    save("native-projections.json.gz",result)
    save("native-run.json",dict(upstream=REV, count=len(result),
        median_s=statistics.median(times), elapsed_s=time.perf_counter()-t0,
        replay_sha256=digest(D/"replay.py"), input_sha256=digest(D/"cases.json.gz"),
        projected_sha256=digest(D/"native-projections.json.gz"),
        predicate_sha256=digest(D/"predicate.json.gz")))
    print("Sealed native projections:",len(result),flush=True)


if __name__=="__main__":
    main()

