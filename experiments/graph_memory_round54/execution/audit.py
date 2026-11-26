"""Replay all executable generated methods, independently check lexical/graph addresses on masked source."""
import numpy as np
from study import *
from isolate import execute
from grade import extracted
from generate import key
def main():
    sel=get("selection.json");inp=get("input-seal.json");ans=get("answer-seal.json");score=get("grade-seal.json")
    checks=[(sel,"observations","observations.json.gz"),(sel,"controls","calibration.json.gz"),(sel,"protocol","PROTOCOL_RU.md"),
        (sel,"code","study.py"),(sel,"runner","isolate.py"),(inp,"code","generate.py"),(inp,"selection","selection.json"),
        (inp,"contexts","contexts.json.gz"),(inp,"prompts","prompts.json.gz"),(ans,"answers","answers.json.gz"),(ans,"inputs","input-seal.json"),
        (score,"code","grade.py"),(score,"unittest","unittest.json.gz"),(score,"results","results.json"),(score,"records","records.json.gz")]
    for receipt,field,f in checks:assert receipt[field]==sha(D/f),f
    rows={r["task_id"]:r for r in dataset()}
    obs=get("observations.json.gz");contexts=get("contexts.json.gz");answers=get("answers.json.gz");prompts=get("prompts.json.gz")
    rec=get("records.json.gz");res=get("results.json");native=get("unittest.json.gz");oracle=get("calibration.json.gz")
    assert set(answers)==set(prompts) and all(key(t)==h for h,t in prompts.items())
    pending={};pairs=0;job_lookup={}
    for q,r in obs.items():
        row=rows[r["task_id"]];target=r["method"];empty=patched(row,target,ast.parse("raise NotImplementedError()").body)
        cls=class_node(empty,r["cls"]);method_info={m["method_name"]:m for m in row["methods_info"]}
        methods={m.name:m for m in cls.body if isinstance(m,ast.FunctionDef) and m.name!=target and not m.name.startswith("__") and m.name in method_info}
        assert r["test_class"]==method_info[target]["test_class"] and oracle[q+"|reference"]["passed"] and not oracle[q+"|blank"]["passed"]
        reverse=sorted(k for k,m in methods.items() if call_edge(m,target,r["cls"]));assert reverse==r["callers"]
        bm=rank(r["cls"]+" "+target+" "+method_info[target]["method_description"].strip(),
          {k:k+"\n"+method_info[k]["method_description"]+"\n"+snippet(m) for k,m in methods.items()})
        assert bm==r["rank"] and r["choices"]=={"caller_bm25":next(k for k in bm if k in reverse),"bm25":bm[0]}
        for k,v in r["evidence"].items():assert v==snippet(methods[k])
        refs=contexts[q]["refs"];assert refs[ARMS[0]][2]==refs[ARMS[1]][2]
        pairs+=refs[ARMS[0]][1]!=refs[ARMS[1]][1]
        for arm,(_id,h,n) in refs.items():
            assert len(prompts[h])==n
            uid=q+"|"+h
            if uid in job_lookup:continue
            job_lookup[uid]=True
            body,tag=extracted(answers[h]["code"],target)
            assert tag==native["parse"][uid]
            if body:pending[uid]=dict(id=uid,src=patched(row,target,body),test=row["test"],suite=r["test_class"])
    assert pairs==res["different"] and set(native["raw"])==set(pending)
    repeat=execute([pending[k] for k in reversed(sorted(pending))],4)
    mismatches={k:[native["raw"][k],v] for k,v in repeat.items() if native["raw"][k]!=v}
    for arm in ARMS:
        assert res["summaries"][arm]["passed"]==sum(rec[q][arm]["pass1"] for q in rec)
    put("repeat-tests.json.gz",repeat)
    report=dict(checked_prompts=len(prompts),assignments=3*len(contexts),verified_methods=len(obs),replayed=len(repeat),
        identical_test_outcomes=len(repeat)-len(mismatches),mismatches=mismatches,replay=sha(D/"repeat-tests.json.gz"),
        plan=sha(D/"AUDIT_PROTOCOL_RU.md"),runner=sha(D/"isolate.py"),code=sha(Path(__file__)))
    put("audit.json",report);print(report)
if __name__=="__main__":main()
