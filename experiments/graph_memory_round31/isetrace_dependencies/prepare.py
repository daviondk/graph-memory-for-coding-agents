"""Check selected real citations bytewise, then save only hashed coordinates, incidence and local BM25 scores."""
from collections import Counter,defaultdict
from pathlib import Path
from time import perf_counter_ns as now
import gzip
import hashlib
import json
import math
import os
import re
import sqlite3

D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r31-isetrace-dependencies")
WHOLE=Path("D:/CodexResearch/x20-r30-witness/ise-events.json.gz");SPL=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/trajectories")
PRIOR=D.parents[1]/"graph_memory_round30/witness_handoff"
def h(b):return hashlib.sha256(b.encode() if isinstance(b,str) else b).hexdigest()
def sha(p):return h(p.read_bytes())
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def save(p,x):
    raw=(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw);os.replace(tmp,p)
def tokens(s):return re.findall(r"[^\W_]+",s.casefold())
def score(query,docs):
    words=[Counter(tokens(s)) for s in docs];n=len(words);avg=sum(sum(w.values()) for w in words)/n or 1
    idf={t:math.log1p((n-df+.5)/(df+.5)) for t in set(tokens(query)) for df in [sum(t in w for w in words)]}
    out=[]
    for w in words:
        norm=1.2*(.25+.75*sum(w.values())/avg)
        out.append(sum(idf[t]*2.2*w[t]/(w[t]+norm) for t in sorted(idf) if t in w))
    return out

def cohort():
    cases=read(WHOLE);chosen={};counts=Counter()
    for r in cases:
        ev=r["events"];atoms=defaultdict(set)
        for j,e in enumerate(ev):
            for line,code,n in e["lines"]:atoms[e["path"],line,code].add(j)
        repeat=any(len(v)>1 for v in atoms.values());m=len(ev)
        if m>=3 or repeat:
            group=("overlap3" if m>=3 else "overlap2") if repeat else "disjoint3"
            chosen[r["id"]]=(group,ev);counts[group]+=1
    assert counts=={"overlap3":67,"overlap2":37,"disjoint3":176}
    return chosen

def make():
    chosen=cohort();qids=sorted(chosen);raw_plan={"protocol":sha(D/"PROTOCOL_RU.md"),"source":sha(WHOLE),"inventory":sha(PRIOR/"ise-byte-audit.json"),
        "qids":qids,"groups":{q:chosen[q][0] for q in qids},"code":sha(Path(__file__)),"K":[1,2,4,8,64],"modes":["raw","producer","atom_group","mask_group","mask_pareto"]}
    if (D/"plan.json").exists():assert read(D/"plan.json")==raw_plan
    else:save(D/"plan.json",raw_plan)
    path=P/sha(D/"plan.json");path.mkdir(exist_ok=True)
    if (D/"source-seal.json").exists():return
    data={};checks={};times={};files={}
    for f in sorted(SPL.glob("trajectories-*.jsonl")):
        digest=hashlib.sha256()
        with f.open("rb") as file:
            for line in file:
                digest.update(line);record=json.loads(line);q=record["session_id"]
                if q not in chosen:continue
                group,ev=chosen[q]
                bycall={}
                for message in record["messages"]:
                    for call in message.get("tool_calls") or []:
                        if call.get("function",{}).get("name")=="read":
                            args=call["function"]["arguments"]
                            try:bycall[call["id"]]=json.loads(args) if isinstance(args,str) else args
                            except (TypeError,ValueError):continue
                atoms={};atom_positions=[];chunks=[];docs=[];rows=[];t=now()
                for j,e in enumerate(ev):
                    m=record["messages"][e["id"]];args=bycall[m["tool_call_id"]]
                    assert m.get("success") and m.get("role")=="tool"
                    loc=next(args[k] for k in ("path","file_path","filePath","file") if isinstance(args.get(k),str))
                    assert h(loc)==e["path"];off=int(args.get("offset",1));content=m["content"].splitlines()
                    ids=[];text=[]
                    for l,d,n in e["lines"]:
                        s=content[l-off];enc=s.encode()
                        assert h(enc)==d and len(enc)==n
                        atom=(e["path"],l,d);idx=atoms.get(atom)
                        if idx is None:
                            idx=len(atoms);atoms[atom]=idx;atom_positions.append([e["path"],l,d,n])
                        ids.append(idx);text.append(s);docs.append(s);rows.append([j,idx])
                    chunks.append((e["id"],ids,text))
                mapping_ns=now()-t
                query=" ".join(str(x["natural_language_intent"]) for x in record["source_intents"])
                t=now();scores=score(query,docs);chunk_scores=score(query,["\n".join(v[2]) for v in chunks]);rank_ns=now()-t
                data[q]={"group":group,"atoms":atom_positions,"events":[[v[0],v[1]] for v in chunks],"line_producer_atom":rows,
                    "line_score":scores,"block_score":chunk_scores}
                checks[q]={"qhash":h(query),"events":len(chunks),"atoms":len(atoms),"appearances":len(rows),
                           "multi_owned_atoms":sum(len({j for j,a in rows if a==idx})>1 for idx in range(len(atoms)))}
                times[q]={"verify_link_ns":mapping_ns,"bm25_ns":rank_ns}
        files[f.name]=digest.hexdigest();print("verified",f.name,len(data),flush=True)
    assert set(data)==set(qids)
    save(path/"input.json.gz",data);save(D/"source-inventory.json.gz",checks);save(D/"source-cost.json.gz",times)
    save(D/"source-seal.json",{"raw_file_sha":files,"plan":sha(D/"plan.json"),"private_input":sha(path/"input.json.gz"),
        "inventory":sha(D/"source-inventory.json.gz"),"cost":sha(D/"source-cost.json.gz"),"sessions":len(data)})
if __name__=="__main__":make()
