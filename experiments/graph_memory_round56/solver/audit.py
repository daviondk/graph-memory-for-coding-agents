"""Audit input identity, inspect possible reuse of test inputs and grade the locked selector."""
from collections import Counter
import io
import itertools
import json
import statistics
import tokenize
from study import *
from generate import key


def norm_tokens(src):
    ts=[]
    try:
        for token in tokenize.generate_tokens(io.StringIO(src).readline):
            if token.type in (tokenize.NAME,tokenize.NUMBER,tokenize.STRING,tokenize.OP):
                if token.type in (tokenize.STRING,tokenize.NUMBER):
                    try:ts.append((token.type,repr(ast.literal_eval(token.string))));continue
                    except (SyntaxError,ValueError):pass
                ts.append((token.type,token.string))
    except (tokenize.TokenError,SyntaxError,IndentationError):pass
    return ts

def target_calls(expr,name):
    try:t=ast.parse(expr)
    except SyntaxError:return []
    return [ast.unparse(x) for x in ast.walk(t) if isinstance(x,ast.Call) and
            ((isinstance(x.func,ast.Name) and x.func.id==name) or (isinstance(x.func,ast.Attribute) and x.func.attr==name))]
def fmatched(needle,h):
    return bool(needle) and any(h[i:i+len(needle)]==needle for i in range(len(h)-len(needle)+1))

def main():
    register=read("witness-seal.json")
    assert all(digest((HERE/n).read_bytes())==v for n,v in register.items())
    records=read("records.json.gz"); extra_records=read("extra-records.json.gz");assigned=read("assignments.json.gz")
    visible=read("visible.json.gz");extra=read("extra-visible.json.gz")
    probes=read("witness-observations.json.gz");choices=read("witness-decisions.json.gz")
    gold=json.loads((RAW/"author-inputs.json").read_bytes());sel=read("selections.json.gz")
    assert all(key(ids)==h for h,ids in read("prompts.json.gz").items()) and all(key(ids)==h for h,ids in read("extra-prompts.json.gz").items())
    per={};hits=Counter();old_inputs=0
    for q,row in records.items():
        name=sel[q]["task"]["name"]
        examples=gold[q]["examples"]
        terms=[norm_tokens(c) for s in examples for c in target_calls(s,name)]
        def same(s):
            tok=norm_tokens(s)
            return any(fmatched(t,tok) for t in terms)
        primary={a:same(s.split("\n",1)[-1]) for a,s in visible[q].items()}
        supplementary={a:same(s.split("\n",1)[-1]) for a,s in extra[q].items()}
        old_hits=sum(same(p["expr"]) for p in probes[q])
        old_inputs+=old_hits
        for a,yes in primary.items():hits[a]+=yes
        per[q]=dict(primary=primary,extra=supplementary,witness_matches=old_hits)
        assert len(set(v["tokens"] for a,v in assigned[q].items() if a!="contract"))==1
    write("overlap-by-task.json.gz",per)
    def stats(group):
        score={}
        for arm in ("old_expected","consensus","full_bm25","pool_oracle"):
            r=[]
            for q in group:
                if arm=="pool_oracle":v=max(records[q].values(),key=lambda x:(x["ok"],x["good"]))
                else:v=records[q][choices[q].get(arm,arm)]
                r.append(v)
            score[arm]=[sum(v["ok"] for v in r),len(r),sum(v["good"] for v in r),sum(v["total"] for v in r)]
        return score
    active=[q for q,c in choices.items() if c["observations"]]
    inspected=read("witness-probes.json.gz")
    out=dict(total_questions=len(sel),answer_hashes=len(read("answers.json.gz")),extra_answer_hashes=len(read("extra-answers.json.gz")),
             exact_input_matches_by_primary_arm=dict(hits),matched_any_primary=sum(any(x["primary"].values()) for x in per.values()),
             matched_any_extra=sum(any(x["extra"].values()) for x in per.values()),
             from_historical_probes=old_inputs,probe_questions=len(active),probe_count=sum(len(v) for v in probes.values()),
             probe_implementation_jobs=len(inspected),probe_executions=sum(len(r.get("values",[])) for r in inspected.values()),
             witness_all=stats(list(sel)),witness_on_covered=stats(active),
             witness_without_repeated_inputs=stats([q for q in sel if not per[q]["witness_matches"]]),
             probe_questions_with_different_outcomes=sum(len(set(c["old_scores"].values()))>1 for c in choices.values()),
             changed_vs_bm25=sum(c["old_expected"]!="full_bm25" for c in choices.values()),
             changed_vs_consensus=sum(c["old_expected"]!=c["consensus"] for c in choices.values()),
             primary_without_repeated_input={a:sum(records[q][a]["ok"] for q in sel if not any(per[q]["primary"].values())) for a in ARMS},
             per_task_changes={q:[v["old_expected"],v["consensus"],records[q][v["old_expected"]]["ok"],records[q][v["consensus"]]["ok"]]
                               for q,v in choices.items() if v["old_expected"]!="full_bm25" or v["consensus"]!="full_bm25"})
    write("audit.json",out);print(out)
if __name__=="__main__":main()
