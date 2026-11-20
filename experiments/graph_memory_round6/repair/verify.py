import hashlib,json,gzip,tarfile,statistics
from pathlib import Path
import grade
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def check():
    ids=read(D/"cohort.json")["ids"]
    summary={"tasks":len(ids),"oracle_pass":0,"oracle_applied":0,"oracle_strict":0,"oracle_regressions":0,"oracle_vs_flat":{"wins":0,"losses":0},"checked_source_files":0,"per_task":[],"tokens":{}}
    for lk in ("input_lock.json","oracle_lock.json"):
        lock=read(D/lk)
        for path,digest in lock.items():
            if path=="packets":
                for i,sh in digest.items():assert hashlib.sha256((D/"tasks"/i/("oracle.json.gz" if lk=="oracle_lock.json" else "packets.json.gz")).read_bytes()).hexdigest()==sh
            else:assert hashlib.sha256((D/path).read_bytes()).hexdigest()==digest,path
    for i in ids:
        d=D/"tasks"/i;g=read(d/"grading.json");base=read(d/"grades_v2/control.json")["base"]["tests"];gold=read(d/"grades_v2/control.json")["gold"]["tests"];assert base["FAIL_TO_PASS"]["complete"] and base["FAIL_TO_PASS"]["failed"] and gold["FAIL_TO_PASS"]["complete"] and not gold["FAIL_TO_PASS"]["failed"]
        orig=grade.paths(g["test_patch"])|grade.paths(g["patch"])|set(read(d/"packets.json.gz")["paths"])
        with tarfile.open(d/"checkout.tar.gz") as f:
            source={}
            for t in f:
                rel=t.name.partition("/")[2]
                if t.isfile() and rel in orig:source[rel]=f.extractfile(t).read()
        for p in orig:
            file=d/"base"/p
            assert (file.read_bytes() if file.exists() else None)==source.get(p),(i,p)
        summary["checked_source_files"]+=len(orig);a=read(d/"grades_v2/solver.json")
        oracle=read(d/"grades_v2/oracle.json")["oracle"]
        f=oracle["tests"]["FAIL_TO_PASS"];rp=oracle["tests"]["PASS_TO_PASS"]
        op=bool(oracle["applied"] and f["complete"] and not f["failed"])
        reg=set(base["PASS_TO_PASS"]["passed"])-set(rp["passed"])
        flat=a["flat"];ff=flat["tests"]["FAIL_TO_PASS"];fp=bool(flat["applied"] and ff["complete"] and not ff["failed"])
        summary["oracle_pass"]+=op; summary["oracle_strict"]+=bool(op and not reg);summary["oracle_applied"]+=oracle["applied"];summary["oracle_regressions"]+=len(reg)
        summary["oracle_vs_flat"]["wins"]+=bool(op and not fp);summary["oracle_vs_flat"]["losses"]+=bool(fp and not op)
        summary["per_task"].append({"id":i,"oracle":op,"changed_without_regressions":not reg,"oracle_tokens":read(d/"oracle.json.gz")["tokens"]})
    import analyse
    pair=summary["oracle_vs_flat"];pair["p"]=analyse.exact(pair["wins"],pair["losses"])
    for folder in ["calls","oracle_calls"]:
        reqs=[read(x) for x in (D/folder).glob("*.gz")]
        for obj in reqs:
            assert obj["response"]["choices"] and obj["response"]["usage"]["prompt_tokens"]>0
        summary["tokens"][folder]={k:sum(obj["response"]["usage"][k] for obj in reqs) for k in ["prompt_tokens","completion_tokens"]}
    (D/"verification.json").write_text(json.dumps(summary,indent=1),encoding="utf8");print({k:v for k,v in summary.items() if k!="per_task"})
if __name__=="__main__":check()

