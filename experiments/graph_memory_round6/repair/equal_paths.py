"""Read the full repeated evaluation with the oracle prompt and primary write permissions."""
import json,gzip,statistics
from pathlib import Path
from analyse import exact
D=Path(__file__).resolve().parent
def obj(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def ok(x):
    f=x["tests"]["FAIL_TO_PASS"];return bool(x["applied"] and f["complete"] and not f["failed"])
def main():
    rows=[]
    for i in obj(D/"cohort.json")["ids"]:
        dest=D/"tasks"/i;regular=obj(dest/"packets.json.gz");special=obj(dest/"oracle.json.gz");g=dest/"grades_v2";oracle=obj(g/"oracle.json")["oracle"];fair=obj(g/"equal.json")["oracle"];flat=obj(g/"solver.json")["flat"]
        reg=set(obj(g/"control.json")["base"]["tests"]["PASS_TO_PASS"]["passed"])-set(fair["tests"]["PASS_TO_PASS"]["passed"])
        assert fair["call_id"]==oracle["call_id"]
        rows.append({"id":i,"extra_paths":sorted(set(special["paths"])-set(regular["paths"])),"applied":fair["applied"],"equal_pass":ok(fair),"oracle_pass":ok(oracle),"flat_pass":ok(flat),"missing_p2p":len(reg),"tokens":special["tokens"]})
    w=sum(r["equal_pass"] and not r["flat_pass"] for r in rows);l=sum(r["flat_pass"] and not r["equal_pass"] for r in rows)
    res={"applied":sum(r["applied"] for r in rows),"passed":sum(r["equal_pass"] for r in rows),"missing_p2p":sum(r["missing_p2p"] for r in rows),"n":len(rows),"wins_vs_flat":w,"losses_vs_flat":l,"p":exact(w,l),"extra_in":sum(bool(r["extra_paths"]) for r in rows),"affected_pass":[r["id"] for r in rows if r["equal_pass"]!=r["oracle_pass"]],"mean_tokens":statistics.mean(r["tokens"] for r in rows),"rows":rows}
    (D/"equal_paths.json").write_text(json.dumps(res,indent=1),encoding="utf8");print({k:v for k,v in res.items() if k!="rows"})
if __name__=="__main__":main()

