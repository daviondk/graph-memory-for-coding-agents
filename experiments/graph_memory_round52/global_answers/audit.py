"""Recompute selected rows, token keys, effects and support cells from sealed local artifacts."""
from prepare import *
import struct,math
def audit():
    reg=load("registration.json");texts=load("texts-seal.json");inp=load("input-seal.json");out=load("answer-seal.json");grade=load("grade-seal.json")
    checks=[(reg,"protocol","PROTOCOL_RU.md"),(reg,"source_code","prepare.py"),(reg,"selection","selection.json.gz"),
        (texts,"selection","selection.json.gz"),(inp,"prompts","prompts.json.gz"),(inp,"contexts","contexts.json.gz"),(inp,"code","answer.py"),
        (inp,"texts","texts-seal.json"),(out,"inputs","input-seal.json"),(out,"answers","answers.json.gz"),
        (grade,"answers","answer-seal.json"),(grade,"records","records.json.gz"),(grade,"results","results.json"),(grade,"code","evaluate.py")]
    for seal,field,file in checks:assert seal[field]==hashfile(HERE/file),(field,file)
    p=read(HERE.parent/"global_policy"/"predictions.json.gz")
    selected=load("selection.json.gz")
    ids=sorted(p,key=lambda i:hashlib.sha256(("r52-global-reader-v1|"+i).encode()).hexdigest())[:384]
    assert set(ids)==set(selected)
    c=load("contexts.json.gz");t=load("prompts.json.gz");a=load("answers.json.gz");grades=load("records.json.gz")
    assert set(t)==set(a) and set(grades)==set(c)==set(ids)
    width=[];unique=set();result=load("results.json")
    for q in ids:
        row=c[q];assert 0<row["first_tokens"]<=192 and 0<row["second_tokens"]<=192
        assert row["first"]==p[q]["seed"]
        assert len({v[2] for v in row["refs"].values()})==1
        for arm,(doc,key,n) in row["refs"].items():
            v=t[key];assert len(v)==n and hashlib.sha256(struct.pack("<"+"I"*len(v),*v)).hexdigest()==key
            assert doc==p[q]["choices"][OUTPUTS.index(arm)] and doc!=row["first"]
            unique.add(key)
    assert unique==set(t)
    for z in ARMS:
        y=result["policies"][z]
        for j,m in enumerate(["f1","em","full","recall"]):
            assert abs(100*math.fsum(grades[q][z][j] for q in ids)/len(ids)-y[m])<1e-9
    for other in ARMS[1:]:
        f=result["comparisons"][other]["f1"];assert abs(f["delta_pp"]-(result["policies"][ARMS[0]]["f1"]-result["policies"][other]["f1"]))<1e-9
    print(f"Verified {len(ids)} selected questions, {len(unique)} GPU answers, {len(ids)*len(ARMS)} matched assignments.")
if __name__=="__main__":audit()
