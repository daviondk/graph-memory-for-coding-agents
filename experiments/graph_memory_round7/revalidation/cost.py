"""Paired batch timings at equal outputs on the fixed transfer panel."""
import ast
import difflib
import hashlib
import json
import platform
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from common import ROOT,Calls,analyze,decode,digest,modules
from predict import affected
from score import oracle

def delta(a,b):
    if b is None:return None,set()
    x=decode(a).splitlines();y=decode(b).splitlines();ops=[];names=set()
    for kind,i,j,k,l in difflib.SequenceMatcher(None,x,y,autojunk=True).get_opcodes():
        if kind=="equal":continue
        ops.append((i,j))
        for line in x[i:j]+y[k:l]:
            tok=re.match(r"^(?:async[ \t]+)?def[ \t]+([^\W\d]\w*)\b",line)
            if tok:names.add(tok[1])
    return ops,names
def workload():
    docs=ROOT/"binding"
    sources={(r["project"],r["version"]):r["name"] for r in json.loads((docs/"sources.json").read_bytes())}
    outcomes={}
    for line in (docs/"outcomes.jsonl").read_text("utf8").splitlines():
        r=json.loads(line)
        if r["panel"]=="transfer":outcomes[r["project"],r["new"],r["path"],r["caller"]]=r["new_answer"]
    groups=defaultdict(lambda:defaultdict(list))
    for line in (docs/"decisions.jsonl").read_text("utf8").splitlines():
        r=json.loads(line)
        if r["panel"]=="transfer":groups[r["project"],r["old"],r["new"]][r["path"]].append(r)
    batches=[];expected=[]
    for (p,old,new),files in groups.items():
        before=modules(sources[p,old]);after=modules(sources[p,new])
        for path,rs in files.items():
            a,b=before[path],after.get(path);g=analyze(a)
            nodes={x.name:x for x in ast.parse(a).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
            stored=[]
            for r in rs:
                n=r["caller"];f=g[n]
                cv=Calls()
                for x in nodes[n].body:cv.visit(x)
                stored.append((n,r["old_answer"],cv.names|{n},[f["full"]]+[g[c]["head"] for c in f["calls"]]))
                expected.append(outcomes[p,new,path,n])
            batches.append((a,b,delta(a,b),stored))
    return batches,expected
def answer_batch(batches,mode):
    output=[]
    for a,b,ready,stored in batches:
        fresh=None
        if mode=="direct":
            fresh=oracle(b)[0]
            output.extend(fresh.get(row[0]) for row in stored)
            continue
        ops,names=delta(a,b) if mode=="compute_delta" else ready
        for n,old,dependencies,intervals in stored:
            reuse=ops is not None and not (names&dependencies) and not any(affected(r,ops) for r in intervals)
            if reuse:output.append(old)
            else:
                if fresh is None:fresh=oracle(b)[0]
                output.append(fresh.get(n))
    return output
def main():
    batches,expected=workload()
    assert len(expected)==717
    modes=["direct","ready_delta","compute_delta"]
    for m in modes:assert answer_batch(batches,m)==expected
    rng=random.Random(70811);rows=[]
    for i in range(7):
        order=rng.sample(modes,len(modes))
        for m in order:
            t=time.perf_counter();cpu=time.process_time();got=answer_batch(batches,m)
            proc=time.process_time()-cpu;wall=time.perf_counter()-t
            assert got==expected
            rows.append(dict(repeat=i,mode=m,wall_s=wall,cpu_s=proc))
    by={}
    for m in modes:
        v=[row["wall_s"] for row in rows if row["mode"]==m]
        by[m]=dict(median_wall=statistics.median(v),min_wall=min(v),max_wall=max(v),median_cpu=statistics.median(row["cpu_s"] for row in rows if row["mode"]==m))
    summary=dict(n=len(expected),file_transitions=len(batches),repeats=rows,metrics=by,python=sys.version,
        platform=platform.platform(),processor=platform.processor(),answer_sha256=digest(json.dumps(expected).encode()),
        script_sha256=digest(Path(__file__).read_bytes()),protocol_sha256=digest((ROOT/"COST_PROTOCOL.md").read_bytes()))
    (ROOT/"cost_results.json").write_text(json.dumps(summary,indent=2)+"\n","utf8")
    print(json.dumps(by))
if __name__=="__main__":main()
