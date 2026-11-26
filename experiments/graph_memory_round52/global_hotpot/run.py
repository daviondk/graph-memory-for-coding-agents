"""Sealed question-only transfer; CPU ranking uses the identical global directory."""
from collections import Counter
from pathlib import Path
import os
import subprocess
import sys
import hashlib
import unicodedata
import re

D=Path(__file__).resolve().parent;GT=D.parent/"global_titles";GP=D.parent/"global_policy";CONF=D.parent/"global_confirm"
HOME_DATA=Path("D:/CodexResearch");S=HOME_DATA/"x20-r52-directory-hotpot";DEV=HOME_DATA/"x20-r52-wiki-directory"
VAL=HOME_DATA/"x20-r31-hotpot/validation.parquet";TRAIN=sorted((HOME_DATA/"x20-r51-hotpot-gate").glob("train-*.parquet"))
N=1280;os.environ["R52_WIKI_WORK"]=str(S)
sys.path.insert(0,str(CONF));sys.path.insert(0,str(GT))
from corpus import read,save,hashfile
from lexicon import tokens
from syntax import choose, ARMS
FILES=("lex.bin","stop.bin","vocab.txt","titles.txt","para_with_hyperlink.zip")
def canon(q):return " ".join(re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",q).casefold()))
def signature(q):return hashlib.sha256(("r52-hotpot-global-v1|"+q).encode()).digest()
def project(path):
    import pyarrow.parquet as pq
    return {r["id"]:r["question"] for b in pq.ParquetFile(path).iter_batches(columns=["id","question"]) for r in b.to_pylist()}
def prep():
    S.mkdir(exist_ok=True);old={}
    for name in FILES:
        if not (S/name).exists():os.link(DEV/name,S/name)
        assert os.path.samefile(DEV/name,S/name);old[name]=hashfile(DEV/name)
    assert old["titles.txt"]==read(GT/"source.json")["titles"] and old["para_with_hyperlink.zip"]==read(GT/"source.json")["archive"]
    assert len(TRAIN)==2
    split=project(VAL);train={q:t for f in TRAIN for q,t in project(f).items()}
    dev=read(DEV/"questions.json.gz");hold=read(HOME_DATA/"x20-r52-directory-confirm/questions.json.gz")
    assert len(split)==7405 and len(train)==90447
    oldkeys=set(train)|set(dev)|set(hold);seen=set(map(canon,[*train.values(),*dev.values(),*hold.values()]))
    chosen={};excluded=Counter()
    for q in sorted(split,key=signature):
        if q in oldkeys:excluded["id"]+=1;continue
        key=canon(split[q])
        if key in seen:excluded["text"]+=1;continue
        seen.add(key);chosen[q]=split[q]
        if len(chosen)==N:break
    assert len(chosen)==N and set(chosen).isdisjoint(oldkeys)
    save(S/"questions.json.gz",chosen);save(D/"questions.json.gz",chosen)
    vocab={s.rstrip("\n"):i for i,s in enumerate((S/"vocab.txt").open(encoding="utf8"))}
    (S/"questions.in").write_bytes("".join(q+" "+" ".join(str(vocab.get(t,0)) for t in tokens(chosen[q]))+"\n" for q in sorted(chosen)).encode())
    save(D/"roster.json",dict(order=list(chosen),inputs=old,questions=hashfile(D/"questions.json.gz"),native_questions=hashfile(S/"questions.in"),code=hashfile(Path(__file__)),
        source=hashfile(VAL),train={f.name:hashfile(f) for f in TRAIN},train_n=len(train),dev_n=len(dev),other_confirm_n=len(hold),
        excluded=dict(excluded),candidate_n=len(split),protocol=hashfile(D/"PROTOCOL_RU.md"),learned_model=hashfile(CONF/"dev-model.json"),
        syntax=hashfile(CONF/"syntax.py"),dev_predictions=hashfile(GP/"prediction-seal.json")))
    print("ROSTER",N,dict(excluded),flush=True)
def native():
    spec=read(CONF/"dev-model.json");assert spec["feature_code"]==hashfile(CONF/"syntax.py")
    retrieval=(GT/"retrieval.cpp").read_text(encoding="utf8");policy=(GP/"policy.cpp").read_text(encoding="utf8")
    assert retrieval.count("if(count!=12576)")==1 and policy.count("if(count!=12576||")==1
    (S/"hp-r.cpp").write_text(retrieval.replace("if(count!=12576)",f"if(count!={N})"),encoding="utf8")
    (S/"hp-p.cpp").write_text(policy.replace("if(count!=12576||",f"if(count!={N}||").replace('"../global_titles/retrieval.cpp"','"hp-r.cpp"'),encoding="utf8")
    for k in ("r","p"):subprocess.run(["g++","-O2","-std=c++17",f"hp-{k}.cpp","-o",f"hp-{k}.exe"],cwd=S,check=True)
    save(D/"kernel.json",{k:hashfile(f) for k,f in dict(upstream_r=GT/"retrieval.cpp",upstream_p=GP/"policy.cpp",effective_r=S/"hp-r.cpp",effective_p=S/"hp-p.cpp").items()})
def execute():
    def call(name,cmd):
        z=subprocess.run(cmd,cwd=S,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(D/(name+".log")).write_bytes(z.stdout);z.check_returncode()
    call("seed",[str(S/"hp-r.exe"),"seed"]);print("SEEDS",flush=True)
    import open_first
    class LocalPaths:
        def __truediv__(self,key):return (GT if key=="retrieval.cpp" else D)/key
    open_first.ROOT=LocalPaths();open_first.extract();print("FIRST EXPOSED",flush=True)
    call("second",[str(S/"hp-r.exe"),"second"]);call("direct",[str(S/"hp-p.exe")])
def table(file):return {q:list(map(int,rest)) for q,*rest in (l.split("\t") for l in (S/file).read_text().splitlines())}
def seal():
    model=read(CONF/"dev-model.json");qs=read(D/"questions.json.gz");opened=read(S/"opened.json.gz")
    second=table("second.tsv");direct=table("policy52-direct.tsv");seeds=table("seed.tsv")
    assert set(second)==set(direct)==set(seeds)==set(qs)==set(read(D/"roster.json")["order"])
    rows={};ids=set();routes=Counter()
    for q in sorted(qs):
        seed,free,plain,_,_,_,literal,href,*_=second[q];gate=direct[q][8:14]
        assert seed==seeds[q][0]==direct[q][0]
        pred,coord,learned=choose(qs[q],opened[str(seed)]["title"],gate,plain,href,literal,free,model)
        assert seed not in pred and min(pred)>=0
        rows[q]=dict(seed=seed,choices=pred,direct_gate=gate,coordination=coord,learned_direct=learned)
        ids.update([seed,*pred]);routes["direct"]+=bool(gate[1]);routes["coord"]+=coord;routes["learned"]+=learned
    names={}
    with (S/"titles.txt").open(encoding="utf8") as f:
        for i,l in enumerate(f):
            if i in ids:
                a,t=l.rstrip("\n").split("\t",1);names[i]=[int(a),t]
    assert len(ids)==len(names)
    save(D/"predictions.json.gz",rows);save(D/"chosen-titles.json.gz",names)
    save(D/"prediction-seal.json",dict(arms=ARMS,n=N,routes=routes,files={s:hashfile(D/s) for s in ("PROTOCOL_RU.md","run.py","roster.json","kernel.json","questions.json.gz","opening.json","predictions.json.gz","chosen-titles.json.gz","seed.log","second.log","direct.log")},cache={n:hashfile(S/n) for n in ("questions.in","seed.tsv","second.in","second.tsv","policy52-direct.tsv","opened.json.gz")}))
    print("SEALED",hashfile(D/"prediction-seal.json"),dict(routes),flush=True)
if __name__=="__main__":
    for fn in (prep,native,execute,seal):fn()
