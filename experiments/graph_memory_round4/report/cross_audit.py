"""Independent check: primary raw calls/ranks and per-function records joined to original target columns."""
import gzip
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime,timezone
from pathlib import Path
import pyarrow.parquet as pq

R=Path(__file__).resolve().parents[1]
D=R/"repo"
def read(p):
    p=Path(p)
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def lines(p):
    with gzip.open(p,"rt",encoding="utf8") as f:
        yield from map(json.loads,f)
def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def require(label,ok):
    if not ok:raise AssertionError(label)
def first_line(s):
    ls=[line.strip() for line in s.splitlines() if line.strip()]
    return next((z for z in ls if not z.startswith("```")),"")
def read_shards(path,nextlines):
    gold=defaultdict(list); projects=set(); manifest={}
    for p in sorted(path.glob("java_*_test_*.parquet")):
        panel=p.stem.rsplit("_",1)[0]
        cols=["repo_name","gold_snippet_index"]+(["next_line"] if nextlines else [])
        table=pq.read_table(p,columns=cols).to_pydict()
        names=table["repo_name"];projects.update(names)
        target=table.get("next_line",[None]*len(names))
        gold[panel].extend(zip(names,table["gold_snippet_index"],target,strict=True))
        manifest[p.name]={"rows":len(names),"sha256":sha(p)}
    return gold, projects, manifest
def decode_calls(folder,sub):
    plans=read(folder/(sub+"_assignment.json"))
    expected=read(folder/(sub+"_decisions.json"))
    output={}
    for cid in {x for a in plans.values() for x in a.values()}:
        name=cid+".json.gz"
        p=folder/(sub+"_calls")/name
        require(name,sha(p)==expected[name])
        resp=read(p)["reply"]
        s=resp["choices"][0]["message"].get("content") or ""
        output[cid]=(first_line(s),resp["usage"]["prompt_tokens"])
    return {row:{arm:output[cid] for arm,cid in arms.items()} for row,arms in plans.items()}
def independent_similarity(a,b):
    if a==b:return 100
    # Bit-parallel exact LCS length for a second implementation of normalized Indel similarity.
    masks={}
    for j,ch in enumerate(b):masks[ch]=masks.get(ch,0)|(1<<j)
    state=0
    for ch in a:
        x=masks.get(ch,0)|state
        state=x & ~(x-((state<<1)|1))
    return round(200*state.bit_count()/(len(a)+len(b)))
def reader(gold):
    work=R/"java_reader"
    full=decode_calls(work,"B"); empty=decode_calls(work,"Z")
    gates=read(work/"selective_choices.json")["B"]
    require("sets reader",set(full)==set(empty)==set(gates))
    short={}; long={}; coverage={}
    for label,rows in (("short",full),("long",decode_calls(R/"java_long","long"))):
        totals=defaultdict(Counter); coverage[label]=len(rows)
        for key,arms in rows.items():
            panel,j=key.split("|"); truth=gold[panel][int(j)][2].strip()
            if label=="short":
                arms={**arms,**empty[key]}
                for a in ["use","random"]:
                    arms[a]=arms["graph"] if gates[key][a] else arms["empty"]
            for name,(prediction,tokens) in arms.items():
                totals[name].update({"exact":int(prediction==truth),"es":independent_similarity(prediction,truth),"tokens":tokens})
        result={a:{"exact":v["exact"],"mean_prompt_tokens":v["tokens"]/len(rows),"mean_edit_similarity":v["es"]/len(rows)} for a,v in totals.items()}
        if label=="short":short=result
        else:long=result
    require("320 reader totals",coverage["short"]==320 and {a:d["exact"] for a,d in short.items()}=={"graph":16,"semlith":18,"empty":6,"random":10,"use":13})
    require("96 oracle",coverage["long"]==96 and long["oracle"]["exact"]==27)
    return {"n":coverage,"short":short,"long":long,"reads_graph":sum(v["use"] for v in gates.values()),"reads_random":sum(v["random"] for v in gates.values())}
def summary(values):
    return {"n":len(values),"hits1":sum(k==1 for k in values),"hits3":sum(k<=3 for k in values),"hits5":sum(k<=5 for k in values),"mrr":statistics.mean(1/k for k in values)}
def external(gold):
    enc=R/"encoder"
    check=read(enc/"prediction_lock.json")
    require("unix lock",check["pred_sha"]==sha(enc/"predictions.jsonl.gz"))
    rc=defaultdict(dict); total=defaultdict(lambda:defaultdict(list))
    for row in lines(enc/"predictions.jsonl.gz"):
        if row["query"] in ("3","10"):
            key=(row["panel"],row["idx"],int(row["query"]))
            rc[key]["unix"]=row["rank"]
    for row in read(D/"paired_decision_lock.json")["runs"]:
        p=D/("paired_"+row["config"]+".json")
        require("binary lock",sha(p)==row["output_sha"])
        for panel,i,k,found,rank in read(p):
            rc[panel,i,k]["semlith"]=rank
    require("graph lock",read(D/"strict_graph_lock.json")["sha256"]==sha(D/"strict_java.pred.jsonl.gz"))
    for panel,i,k,repo,sz,h,n,arms in lines(D/"strict_java.pred.jsonl.gz"):
        if (panel,i,k) in rc:
            rc[panel,i,k]["graph"]=arms["graph"]
            require("ID alignment",gold[panel][i][0]==repo)
    roster=read(D/"paired_roster.json")
    require("external roster",set(rc)=={(p,i,k) for p,v in roster.items() for i in v for k in (3,10)})
    for (panel,i,k),methods in rc.items():
        require("same external arms",set(methods)=={"unix","semlith","graph"})
        target=gold[panel][i][1]
        ref=sorted(methods["unix"])
        for arm,order in methods.items():
            require("candidate pool",sorted(order)==ref==list(range(len(order))))
            total[k][arm].append(1+order.index(target))
    result={str(k):{name:summary(v) for name,v in methods.items()} for k,methods in total.items()}
    for k,expect in [("3",[81,70,88]),("10",[61,62,97])]:
        require("external Top1", [result[k][a]["hits1"] for a in ("unix","semlith","graph")]==expect)
    return result
def repair():
    rows=read(R/"repair/per_task.json.gz")
    statuses=read(R/"repair/full_suite_items.json.gz")
    require("repair no duplicate",len(rows)==len({r["id"] for r in rows})==64)
    require("repair identifiers",{r["id"] for r in rows}=={r["id"] for r in statuses})
    result={}
    for a in ["qwen_empty","qwen_failed","qwen_union"]:
        n_pass=old=passed=0
        for r in rows:
            m=r["methods"][a]
            hit=int(m["new"]==r["n"] and m["status"]=="ok")
            require("Python hit recomputed",hit==m["hit"])
            n_pass+=hit;passed+=m["new"];old+=int(hit and m["old"]==r["historical"])
        result[a]={"all_new":n_pass,"new_passed":passed,"old_and_new":old,"human_all":sum(x["tests"]["human"][a]["status"]=="pass" for x in statuses),"plus_all":sum(x["tests"]["plus"][a]["status"]=="pass" for x in statuses)}
    require("64 repair",[v["all_new"] for v in result.values()]==[43,53,53])
    require("same solved set",all(r["methods"]["qwen_failed"]["hit"]==r["methods"]["qwen_union"]["hit"] for r in rows))
    return {"n":len(rows),"test_inputs":sum(r["n"] for r in rows),"historical":sum(r["historical"] for r in rows),"arms":result}
def whole(gold,archive):
    prefix="archive" if archive else "full"
    lock=D/(prefix+"_decision_lock.json")
    if not lock.exists():return {"status":"awaiting sealed shard manifest"}
    seen=set(); metrics=defaultdict(lambda:defaultdict(list))
    folder=D/("archive_full" if archive else "full")
    for sh in read(lock)["shards"]:
        p=folder/sh["file"]
        require("full shard hash",sha(p)==sh["hash"])
        for panel,i,project,h,arms in lines(p):
            require("unique full keys",(panel,i) not in seen);seen.add((panel,i))
            name,correct,_=gold[panel][i];require("full project",project==name)
            for a,order in arms.items():
                require("candidate permutation",sorted(order)==list(range(len(order))))
                metrics[panel][a].append(1+order.index(correct) if correct in order else float("inf"))
    require("full count",len(seen)==sum(map(len,gold.values())))
    out={s:{a:summary(v) for a,v in d.items()} for s,d in metrics.items()}
    for key in ("easy","hard","all"):
        panels=[p for p in metrics if key=="all" or p.endswith("_"+key)]
        out[key]={a:summary([v for p in panels for v in metrics[p][a]]) for a in metrics[panels[0]]}
    report=D/(prefix+"_results.json")
    if report.exists():
        official=read(report)
        for a,z in out["all"].items():
            ours=[z["hits1"]/z["n"],z["hits3"]/z["n"],z["hits5"]/z["n"],z["mrr"]]
            theirs=official["all"]["metrics"][a]
            require("full aggregate agreement",max(abs(x-y) for x,y in zip(ours,theirs,strict=True))<1e-10)
    return {"all":out.pop("all"),"strata":out,"source":str(lock.relative_to(R)),"compared_to_summary":report.exists()}
def main():
    gh,ph,mh=read_shards(D/"inputs",True);ga,pa,ma=read_shards(D/"archive_inputs",False)
    roster=read(D/"roster.json");pt=set();nt=0
    for p in sorted((D/"inputs").glob("java_*_train_*.parquet")):
        indices=[j for j,_ in roster[p.stem]]
        names=pq.read_table(p,columns=["repo_name"]).column(0)
        pt.update(names.take(indices).to_pylist());nt+=len(indices)
    panels={"archive_rows":sum(map(len,ga.values())),"hf_rows":sum(map(len,gh.values())),"archive_projects":len(pa),"hf_projects":len(ph),"train_rows":nt,"train_projects":len(pt),"archive_hf_common":len(pa&ph),"archive_train_common":len(pa&pt),"hf_train_common":len(ph&pt),"manifests_sha":{"archive":ma,"hf":mh}}
    require("36k 24k project split",[panels[n] for n in ("archive_rows","hf_rows","archive_hf_common","archive_train_common","hf_train_common")]==[36000,24000,0,0,0])
    out={"utc":datetime.now(timezone.utc).isoformat(),"independent_script_sha256":sha(Path(__file__)),"datasets":panels,"reader":reader(gh),"external":external(gh),"repair":repair(),"archive":whole(ga,True),"full_hf":whole(gh,False)}
    out["status"]="passed"
    dest=R/"report/final/cross_audit.json"
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding="utf8")
    print("PASS",dest,out["archive"].get("status","archived figures validated"))
if __name__=="__main__":main()

