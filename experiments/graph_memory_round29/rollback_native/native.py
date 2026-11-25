"""Native no_repair -> original result writer -> original deterministic oracle / metrics."""
from pathlib import Path
import json,sys,subprocess,gzip,hashlib
from fetch import D,P,SRC,REV
def readl(p):return [json.loads(s) for s in p.read_text(encoding="utf8").splitlines() if s]
def one(cmd,log):
    with log.open("w",encoding="utf8") as out:
        pr=subprocess.run([sys.executable,str(D/"offline_entry.py"),*map(str,cmd)],stdout=out,stderr=subprocess.STDOUT,text=True)
    if pr.returncode:raise RuntimeError(str(log)+"\n"+log.read_text(encoding="utf8")[-1600:])
def run(panel,smoke):
    root=SRC/"data"/("controlled_benchmark" if panel=="controlled" else "adapted_lmev2_subset");registry=readl(root/"registry.jsonl");rows=[min(registry,key=lambda r:hashlib.sha256(r["case_id"].encode()).hexdigest())] if smoke else registry
    work=P/("smoke" if smoke else "native")/panel;work.mkdir(parents=True,exist_ok=True)
    folder=work/"outputs";fmt=str(folder/"{method}"/"{domain}"/"{fault_types}"/"{task_id}"/"{faulty_memory_ids}")
    tail=["--case_id",rows[0]["case_id"]] if smoke else ["--all_cases"]
    one(["baselines/run_baseline.py","--baseline","no_repair","--registry",root/"registry.jsonl","--output_dir",fmt,*tail],work/"native.log")
    one(["eval/run_oracle.py","--results",folder,"--data-root",root,"--output-dir",work/"oracle"],work/"oracle.log")
    pth=work/"oracle/oracle_results.jsonl";judg=work/"oracle/oracle_judgments.jsonl";oracle=readl(pth)
    assert len(oracle)==len(rows)
    for domain in sorted({r["domain"] for r in rows}):
        one(["eval/metrics.py","--ground-truth",root/domain/"ground_truth.jsonl","--results",folder/"no_repair"/domain,"--human-judgments",judg,"--output",work/(domain+"-metrics.json")],work/(domain+"-metrics.log"))
    print(panel,"smoke" if smoke else "full",len(rows),"native results, native domain oracle and metrics saved")
if __name__=="__main__":run(sys.argv[1],sys.argv[2]=="smoke")

