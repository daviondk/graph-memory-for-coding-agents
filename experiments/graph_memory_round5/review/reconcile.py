"""Compare two independently derived result tables row by row; save the number of explicitly matched fields."""
import datetime
import json
from pathlib import Path
from audit_reader import HERE, READER, check, digest, read


def main():
    results={}
    for panel in ("A","B","C","F"):
        raw=read(HERE/f"{panel}_audit_items.json.gz")
        other=read(READER/f"{panel}_items.json.gz")
        calculations={row["id"]:row["methods"] for row in other}
        check(set(calculations)=={row["id"] for row in raw}, "case keys")
        n_fields=n_cells=0
        for row in raw:
            theirs=calculations[row["id"]]; ours=row["arms"]
            check(set(ours)==set(theirs), "arm set")
            for a, v in ours.items():
                w=theirs[a]
                comparison={"em":v["em"]==w["em"],"es":v["es"]==w["es"],"id_f1":abs(v["id_f1"]-w["id_f1"])<1e-10,
                            "prompt_tokens":v.get("final_input",v.get("prompt_tokens"))==w["prompt_tokens"],"finish":v["finish"]==w["finish"],
                            "physical_call":v["cid"]==w["call"],"literal_external":int(v["external"]["exact"])==w["external_copy"]}
                if panel=="F":
                    comparison["depth"]=row["depths"][a]==w["slots"]
                if panel in ("C","F") and a!="empty":
                    comparison["addr_hit"]=int(v["address_hit"])==w["hit"]
                for k,good in comparison.items():
                    check(good,f"mismatch: {panel} {row['id']} {a} {k}")
                n_fields+=len(comparison); n_cells+=1
        results[panel]={"reader_sha256":digest(READER/f"{panel}_items.json.gz"),"independent_sha256":digest(HERE/f"{panel}_audit_items.json.gz"),
                        "matching_rows":len(raw),"matching_arm_rows":n_cells,"matching_fields":n_fields}
    results["utc"]=datetime.datetime.now(datetime.UTC).isoformat()
    results["script_sha256"]=digest(Path(__file__))
    (HERE/"reconciliation.json").write_text(json.dumps(results,indent=1),encoding="utf8")
    print(results)
if __name__=="__main__":main()

