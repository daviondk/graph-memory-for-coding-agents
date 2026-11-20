"""Independent labels opened only after the full slate has been committed."""
from pathlib import Path
import gzip
import json
import statistics
import sys
import duckdb

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
import evaluate as e

def pair(rows,a,b,key):
    adapted=[{"arms":{k:{"hit":v[key]} for k,v in r["arms"].items()}} for r in rows]
    return e.paired(adapted,a,b)

def main():
    lock=e.read(D/"predictions.lock.json")
    assert lock["selection_code"]==e.sha((D/"select_frontier.py").read_bytes())
    assert lock["reader_code"]==e.sha((D.parent/"predict.py").read_bytes())
    assert lock["protocol"]==e.sha((D/"PROTOCOL_RU.md").read_bytes())
    for t,h in lock["predictions"].items():assert e.sha((D/"predictions"/(t+".json.gz")).read_bytes())==h
    e.D=D
    cohort=e.read(D/"cohort_sphinx.json")
    assert cohort["data_sha"]==e.sha(e.DB.read_bytes())
    db=duckdb.connect()
    raw=db.execute("select instance_id,patch from read_parquet(?) where repo='sphinx-doc/sphinx'",[str(e.DB)]).fetchall()
    gold=dict(raw)
    rows=[]
    for task in cohort["ids"]:
        p=json.loads(gzip.decompress((D/"predictions"/(task+".json.gz")).read_bytes()))
        sites,excluded=e.external_sites(task,gold[task])
        row={"id":task,"target_old_lines":len(sites),"sites":sorted(sites),"outside":excluded,"arms":{},"nominated_imports":len(p["nominated_imports"])}
        for arm,a in p["arms"].items():
            assert len(a["paths"])<=8 and a["tokens"]<=1800
            fs=sum(s in a["paths"] for s,n in sites)
            bs=e.intersect(sites,e.mask(a["available"]));ps=e.intersect(sites,e.mask(a["kept"]))
            assert 0<=ps<=bs<=fs<=len(sites)
            row["arms"][arm]={"file":int(fs>0),"block":int(bs>0),"packet":int(ps>0),"lines_in_files":fs,"lines_in_packet":ps,"files_shown":len(a["paths"]),"tokens":a["tokens"]}
        row["import_changed_set"]=set(p["arms"]["rare"]["paths"])!=set(p["arms"]["import"]["paths"])
        rows.append(row)
    keys=["file","block","packet","lines_in_files","lines_in_packet","files_shown","tokens"]
    total={"n":len(rows),"target_old_lines":sum(r["target_old_lines"] for r in rows),"with_target_lines":sum(bool(r["target_old_lines"]) for r in rows),"file_sets_changed_by_import":sum(r["import_changed_set"] for r in rows),
    "arms":{arm:{k:sum(r["arms"][arm][k] for r in rows) for k in keys} for arm in ("old","init","rare","import")},"comparisons":{}}
    for a,b in [("import","rare"),("init","old"),("rare","init"),("import","old")]:
        total["comparisons"][a+"-"+b]={m:pair(rows,a,b,m) for m in ["file","packet"]}
    e.save(D/"results.json",total);e.save(D/"scores_per_issue.json",rows)
    e.save(D/"evaluation.lock.json",{name:e.sha((D/name).read_bytes()) for name in ["predictions.lock.json","grade_frontier.py","results.json","scores_per_issue.json"]}|{"evaluator_sha":e.sha((D.parent/"evaluate.py").read_bytes())})
    print(json.dumps(total,indent=2))
if __name__=="__main__":main()
