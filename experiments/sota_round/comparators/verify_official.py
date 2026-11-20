"""Run the authors' unmodified numerical metrics over the archived provider outputs."""
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from urllib.request import urlopen
from rescore import ROOT, QA_ARMS, jsonl, key

BASE = "https://raw.githubusercontent.com/xiaowu0162/LongMemEval/9e0b455f4ef0e2ab8f2e582289761153549043fc/"


def source(local, remote):
    with urlopen(BASE + remote, timeout=60) as response:
        data = response.read()
    path = ROOT / local
    if path.exists() and path.read_bytes() != data:
        raise ValueError("local upstream scorer has changed")
    path.write_bytes(data)
    return path


def main():
    import numpy
    ret = source("official_retrieval.py","src/retrieval/eval_utils.py")
    qa = source("official_qa_metrics.py.txt","src/evaluation/print_qa_metrics.py")
    spec = importlib.util.spec_from_file_location("upstream",ret)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    refs = key(json.loads((ROOT/"official_scoring_metadata.json").read_bytes()))
    papr = key(jsonl("papr_ranks.jsonl"))
    all_ranks = {"papr": {q:r["top20_session_ids"] for q,r in papr.items()}}
    for arm in ["A1","A2"]:
        values = key(jsonl(f"gbrain_{arm}.ndjson.gz"))
        all_ranks[f"gbrain_{arm}"] = {q:[x["session_id"] for x in sorted(r["retrieved"], key=lambda x:x["rank"])] for q,r in values.items()}
    checked = 0
    with (ROOT/"recount_per_question.csv").open() as stream:
        for row in csv.DictReader(stream):
            arm, k = row["arm"].rsplit("@",1)
            q = row["question_id"]
            ids, gold = refs[q]["haystack_session_ids"],refs[q]["answer_session_ids"]
            ranking = [ids.index(i) for i in all_ranks[arm][q]]
            anyhit, allhit, _ = mod.evaluate_retrieval(ranking,gold,ids,int(k))
            assert float(row["recall_all"]) == allhit and float(row["recall_any"]) == anyhit
            checked += 1
    grades = {}
    for arm in QA_ARMS:
        proc=subprocess.run([sys.executable,"-X","utf8",str(qa),str(ROOT/f"papr_{arm}.grades.jsonl"),str(ROOT/"official_scoring_metadata.json")],
                            check=True,capture_output=True,text=True,encoding="utf8",env=os.environ.copy())
        grades[arm]=proc.stdout.strip()
    record={"revision":BASE,"numpy":numpy.__version__,"case_cutoff_pairs_verified":checked,"any_all_binary_agreement":True,
            "sha256_eval_utils":hashlib.sha256(ret.read_bytes()).hexdigest(),"qa_stdout":grades}
    (ROOT/"official_verification.json").write_text(json.dumps(record,indent=2),encoding="utf8")
    print(checked,"case/cutoff pairs passed; archived QA labels printed by all four official scorer invocations.")


if __name__=="__main__":
    main()
