"""Check identity, independent accounting and signed deliverables."""
from support import *
import sys
def main():
    plan=load(D/"plan.json");states=load(D/"cases.json.gz");results=load(D/"results.json")
    assert sha(D/"cases.json.gz")==results["case_sha"] and sha(D/"plan.json")==results["plan"] and sha(D/"source.sqlite3")==plan["source"]
    db=source();assert db.execute("PRAGMA integrity_check").fetchone()==("ok",) and db.execute("SELECT count(*) FROM events").fetchone()==(plan["n_events"],);db.close()
    logs,order,hashes=original();assert hashes==plan["operations"] and order==plan["id_hashes"]
    for row,case in zip(states,plan["cases"],strict=True):
        assert all(row[k]==v for k,v in case.items()) and row["crash_pid"]!=row["restart_pid"]
        b,off=case["barrier"],case["received"];log=logs[case["history"]]; after=log[b:off];r=row["branches"]["replay"]
        assert r["reread_rows"]==len(after) and r["idempotent_ignores"]==sum(len(x[3]) for x in after) and r["reread_down"]==sum(len(x[4]) for x in after)
        assert not any(any(v) for v in r["reads"]+[r["terminal"]])
        # The naive path permanently retains unrepeated lost pairs in this panel.
        naive=row["branches"]["naive"];assert naive["next"][1]==0 and naive["terminal"][1]==0
    for m in ("post","uncommitted_first"):
        stat=results["groups"][m];r=stat["methods"]["replay"];assert r["next_mismatch"]==r["terminal_mismatch"]==r["wrong_reads"]==0
    manifest=D/"manifest.json"
    if "--seal" in sys.argv:
        save(manifest,{"algorithm":"SHA-256","files":{p.name:sha(p) for p in sorted(D.iterdir()) if p.is_file() and p!=manifest}})
    files=load(manifest)["files"];assert set(files)=={p.name for p in D.iterdir() if p.is_file() and p!=manifest}
    for name,h in files.items():assert sha(D/name)==h,name
    print(len(states),"paired cases;",len(files),"files;",sha(manifest))
if __name__=="__main__":main()
