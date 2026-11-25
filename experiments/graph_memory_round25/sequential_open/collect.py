"""Replay complete sequential read decisions with a state that sees only previous returns."""
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
import sqlite3
import sys

D = Path(__file__).resolve().parent
R24 = D.parents[1] / "graph_memory_round24"
sys.path.insert(0, str(R24 / "frontier_open"))
from routes import S, M, CACHE, TOK, Tokenizer, c, read, write, sha, paid_open, trim
from policy import lexical_features, rank, choose, observe, terms

METHODS = ("first","frozen","any","balanced","tail")
PRIMARY_BUDGET = 768

def replay(q, question, initial, sizes, fields, tokenizer, expected, features):
    wanted = set(terms(question))
    frozen = [(e,offset) for _,e,offset in rank(wanted,initial,features)[0]]
    @lru_cache(maxsize=48)
    def fetch(field, start):
        return paid_open(tokenizer, fields[field], field, start)
    histories = {}
    for method in METHODS:
        state = list(initial)
        actions = []
        counts = Counter()
        for _ in range(4):
            addr = choose(method,state,sizes,counts,wanted,frozen,features)
            if addr is None:
                break
            e,start = addr
            item = fetch(e,start)
            field,left,right,paid = item
            assert (field,left) == addr and 0 < paid <= 256 and right > left
            assert all(field!=src or not (a<=left<a+len(s)) for src,a,s in state)
            state = observe(state,field,left,fields[field][left:right])
            counts[field] += 1
            actions.append(item)
        assert len({(e,l) for e,l,_,_ in actions}) == len(actions)
        histories[method] = actions
    for name,old in (("first","first_edge"),("any","right_edge"),("frozen","right_edge"),("balanced","right_edge")):
        assert (histories[name][0] if histories[name] else None) == expected[old], (q,name)

    def prefix(actions,cap):
        remaining=cap
        result=[]
        for a in actions:
            if remaining <= 0:
                break
            if a[3] <= remaining:
                result.append(a)
                remaining-=a[3]
            else:
                clipped=trim(tokenizer,fields,a,remaining)
                result.append(clipped)
                break
        assert sum(a[3] for a in result)<=cap
        return result

    primary = {k:prefix(v,PRIMARY_BUDGET) for k,v in histories.items()}
    matched = {}
    for right in ("any","balanced","frozen","first"):
        cap=min(sum(a[3] for a in primary[k]) for k in ("tail",right))
        left_plan=prefix(histories["tail"],cap);right_plan=prefix(histories[right],cap)
        # If tokenization of a boundary charges less, lower the common cap until exact.
        for _ in range(16):
            costs=[sum(a[3] for a in v) for v in (left_plan,right_plan)]
            if costs[0]==costs[1]:break
            cap=min(costs);left_plan=prefix(histories["tail"],cap);right_plan=prefix(histories[right],cap)
        assert sum(a[3] for a in left_plan)==sum(a[3] for a in right_plan)
        matched[right]=[left_plan,right_plan]
    return {"base":[[e,l,l+len(s)] for e,l,s in initial],"actions":histories,
            "cap":primary,"equal":matched}

def ise(i):
    tokenizer=Tokenizer.from_file(str(TOK));features=lexical_features(tokenizer)
    visible=Path("D:/CodexResearch/x20-isetrace-fine-train/marginal-open")/f"visible-{i}.json.gz"
    assert sha(visible)==read(M/"visible-seal.json")["parts"][i]["visible"]
    official=read(R24/"frontier_open/actions-isetrace.json.gz")
    source_reg=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    sizes_db=sqlite3.connect((M/"field-lengths.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    by=defaultdict(list)
    for row in read(visible):by[row["t"]].append(row)
    out={}
    for trace,rows in by.items():
        src=read(CACHE/f"{i}-{trace}.json.gz")["fields"]
        lengths=dict(sizes_db.execute("select e,n from field_size where t=?",(trace,)))
        fields={e:src[eid] for e,eid in source_reg.execute("select e,eid from address where t=?",(trace,))}
        for r in rows:
            q=r["q"]
            out[q]=replay(q,r["question"],r["fragments"],lengths,fields,tokenizer,official[q]["actions"],features)
            out[q]["trace"]=trace
    source_reg.close();sizes_db.close()
    target=D/f"ise-{i}.json.gz";write(target,out)
    return target.name,sha(target)

def md():
    tok=c.tok();features=lexical_features(tok);view=c.get_views()
    qs={r[0]:r[2] for r in view["q"]};fields={i:d[2] for i,d in enumerate(view["documents"])}
    lengths={e:len(text) for e,text in fields.items()}
    src=S/"marginal_transfer/actions.json.gz"
    assert sha(src)==read(S/"marginal_transfer/forecast-seal.json")["predictions"]
    old=read(R24/"frontier_open/actions-multidoc.json.gz")
    out={}
    for q,row in read(src).items():
        initial=[(d,l,fields[d][l:h]) for d,l,h in row["base"]]
        out[q]=replay(q,qs[q],initial,lengths,fields,tok,old[q]["actions"],features)
    target=D/"md.json.gz";write(target,out)
    return target.name,sha(target)

def main():
    prereq=read(R24/"frontier_open/action-lock.json")
    for f,digest in prereq["files"].items(): assert sha(R24/"frontier_open"/f)==digest
    with ProcessPoolExecutor(2) as pool:
        fut=pool.submit(md)
        files=dict(pool.map(ise, range(8)))
        filename,h=fut.result();files[filename]=h
    write(D/"sequence-lock.json", {"protocol":sha(D/"PROTOCOL_RU.md"),"collector":sha(Path(__file__)),
          "policy":sha(D/"policy.py"),"parent":sha(R24/"frontier_open/action-lock.json"),"files":files})
    print("Sealed",len(files),"files",flush=True)
if __name__=="__main__":main()
