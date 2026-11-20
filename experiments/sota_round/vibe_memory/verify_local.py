"""Offline verification for the distributed official outputs, costs and existence counts."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent


def main():
    metrics=json.loads((ROOT/"results.json").read_bytes())
    rows=[json.loads(line) for line in (ROOT/"stage_rows.jsonl").read_bytes().splitlines()]
    assert len(rows)==len({(r["instance_id"],r["method"]) for r in rows})==333
    audit=json.loads((ROOT/"path_results.json").read_bytes())
    probes=[json.loads(line) for line in (ROOT/"path_rows.jsonl").read_bytes().splitlines()]
    assert len(probes)==333
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(ROOT/"path-protocol.md")==audit["protocol_sha256"]
    assert digest(ROOT/"stage_outputs.zip")==audit["stage_zip_sha256"]
    with ZipFile(ROOT/"stage_outputs.zip") as z:
        assert z.testzip() is None and len(z.namelist())==666
        for r in rows:
            root=f"{r['method']}/{r['language']}/{r['instance_id']}/"
            src=json.loads(z.read(root+"memory.json"))
            txt=z.read(root+"memory.txt").decode()
            assert len(txt.split())==r["words_with_header"]
            source=src["retrieved"][0]
            assert hashlib.sha256(source["content"].encode()).hexdigest()==r["content_sha256"]
            sid=source["source_session_id"]
            assert int(sid.rsplit("-",1)[1])<int(r["instance_id"].rsplit("-",1)[1])
            assert sid.rsplit("-",1)[0]==r["instance_id"].rsplit("-",1)[0]
    for method,stats in metrics["by_method"].items():
        select=[r for r in rows if r["method"]==method]
        for field in ("stored_text_bytes","source_histories","source_messages","stored_records","words_with_header","retrieved"):
            assert sum(r[field] for r in select)==stats[field]["sum"]
        issue_paths=[r for r in probes if r["method"]==method]
        assert all(len({p["path"] for p in r["paths"]})==len(r["paths"])<=3 for r in issue_paths)
        facts=audit["by_method"][method]
        assert facts["with_confirmed_path"]==sum(any(x["exists"] for x in r["paths"]) for r in issue_paths)
        assert facts["confirmed_paths"]==sum(x["exists"] for r in issue_paths for x in r["paths"])
    print("Verified 333 source-linked memory outputs, 333 path rows, and all published totals.")


if __name__=="__main__":
    main()
