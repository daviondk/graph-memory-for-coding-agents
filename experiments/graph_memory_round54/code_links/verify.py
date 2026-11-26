"""Independently verify returned file IDs and metrics, plus small scope-resolution regressions."""
from collections import Counter,defaultdict
from pathlib import Path
from sources import HERE,load,save,hashfile,archive
from edges import parse,connected,changed_names
import json

def syntax_tests():
    repo="org/work";go=lambda p,s:parse(p,s,repo)
    one=go("pkg/a.go","package abc\n");two=go("pkg/b.go","package abc\n");other=go("pkg/c.go","package abc_test\n")
    assert connected(one,two,repo)=="declared_package" and not connected(one,other,repo)
    cli=go("cmd/a.go",'package main\nimport ab "github.com/org/work/pkg"\n')
    assert connected(cli,one,repo)=="explicit" and not connected(one,cli,repo)
    a=go("src/pkg/first.py","from .next import Tool as MyTool\n");b=go("src/pkg/next.py","")
    assert connected(a,b,repo)=="explicit" and not connected(b,a,repo)
    ta=go("lib/use.ts","import { f as alias } from './other';");tb=go("lib/other.ts","")
    assert connected(ta,tb,repo)=="explicit"
    x=go("x/A.java","package org.x;\nimport org.z.Z;");y=go("z/Z.java","package org.z;")
    assert connected(x,y,repo)=="explicit"
    words,declared,loc=changed_names("@@ -10,2 +10,2 @@\n-foo(thing)\n+foo(thing2)\n+const Added = 'src/internal/paths.py'")
    assert {"foo","thing2"}<=words and declared=={"Added"} and 10 in loc and "internal" not in words
def main():
    syntax_tests()
    seal=load(HERE/"prediction-seal.json");assert all(hashfile(HERE/k)==v for k,v in seal["files"].items())
    pred=load(HERE/"forecasts.json.gz");labels=load(HERE/"graded-rows.json.gz");summary=load(HERE/"results.json")["overall"]
    need=defaultdict(set)
    rows=[]
    for q,p in pred.items():
        gt=set(labels[q]["gold"]);assert gt and p["anchor"] not in gt
        needed=need[p["repo"].replace("/","__"),p["commit"]];needed.add(p["anchor"])
        for arm,rank in p["predictions"].items():
            assert len(rank)==len(set(rank))==20 and p["anchor"] not in rank
            needed.update(rank)
            positions=[(rank.index(x)+1) if x in rank else 99999 for x in gt]
            h5=sum(n<=5 for n in positions);rec=h5/len(positions)
            assert rec==labels[q]["graded"][arm]["recall5"] and bool(h5)==bool(labels[q]["graded"][arm]["hit5"])
            assert ((1/min(positions)) if min(positions)<=20 else 0)==labels[q]["graded"][arm]["mrr20"]
            rows.append((arm,rec))
    from itertools import groupby
    for arm,g in groupby(sorted(rows),key=lambda e:e[0]):
        x=[v for _,v in g];assert abs(sum(x)/len(x)-summary["metrics"][arm]["recall5"])<1e-10
    with archive() as t:
        for m in t:
            if not m.name.startswith("./corpus/") or not m.name.endswith(".chunks.jsonl"):continue
            k=(m.name.split("/")[-2],m.name.split("/")[-1].split(".")[0])
            if k not in need:continue
            paths={r["path"] for l in t.extractfile(m) if (r:=json.loads(l))["kind"]=="file"}
            assert need.pop(k)<=paths
    assert not need
    result={"verified_pairs":len(rows),"official_catalogue_files_and_given_paths":True,"unique_twenty_and_anchor_excluded":True,
            "exact_recovery_of_task_MRR_and_Recall":True,"static_scope_regressions":"PASS","state":"PASS"}
    save(HERE/"audit.json",result);print(result)
if __name__=="__main__":main()

