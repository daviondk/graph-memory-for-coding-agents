"""Check manuscript tables and timing examples against frozen measurements."""
import gzip
import hashlib
import json
from pathlib import Path
import re
from statistics import median
import sys
import fitz

HERE=Path(__file__).resolve().parent
R=HERE.parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

with fitz.open(HERE/"paper.pdf") as doc:
    assert len(doc)==4 and all(tuple(p.rect)==(0,0,612,792) for p in doc)
    text="\n".join(p.get_text() for p in doc)
    words=[len(p.get_text("words")) for p in doc]
    assert all(n>450 for n in words) and all(30<x[1]<x[3]<752 for p in doc for x in p.get_text("blocks"))
    assert all(x in text for x in ("Fig. 1.","Fig. 2.","TABLE I","TABLE II","REFERENCES"))
    assert "??" not in text and chr(65533) not in text
    assert len(re.findall(r"(?m)^\[[1-6]\]",text.split("REFERENCES")[-1]))==6
    fonts={f[0] for p in doc for f in p.get_fonts(full=True)}
    assert all(doc.extract_font(i)[-1] for i in fonts)
m=read(R/"holdout/results.json")
for key,costs in {"B":((27411,21957,20055),(5911,5911,7725)),"long":((4006,3746,4048),(3520,3520,3951))}.items():
    group=m["sketch"]["groups"][key]
    for cap,targets in zip((1024,4096),costs):
        nums=[group[f"{cap}/{name}"]["charged"] for name in ("joint","exact","xor")]
        assert list(targets)==nums and all(f"{n:,}" in text for n in nums)
g=m["sketch"]["groups"]["B"]
assert g["1024/xor"]["recovered1"]==51 and g["1024/xor"]["posting_bytes"]-g["1024/exact"]["posting_bytes"]==914
assert g["1024/exact"]["body_bytes"]-g["1024/xor"]["body_bytes"]==2816
for panel,project,ns in [("B","dense",(41640,41214,36941,36589)),("long","sparse",(11389,10963,6690,5708))]:
    nums=[m["reference"][panel]["full"]["demand1024/"+a]["charged"] for a in ("copy","compressed","eager","lazy")]
    assert nums==list(ns) and all(f"{n:,}" in text for n in nums)
z=read(R/"reference_audit/results.json")
assert sum(c["queries"] for c in z["panels"].values())==2940
pkg=read(R/"references/results.json")["groups"]["original/long"]["full"]
assert [pkg["demand1024/"+n]["charged"] for n in ("copy","compressed","eager","lazy")]==[82907,82729,79902,79893]
f=read(R/"fast_path/results.json")["measures"]
for rule,n,ms in [("append",22186,"56.32"),("xor_native",20063,"57.87")]:
    x=f["1024/"+rule]
    assert x["bytes"]==[n]*3 and f"{median(x['combined_ns'])/1e6:.2f}"==ms and ms in text
transport=read(R/"transport/results.json")
for name,delay,byte,rpc,timing in [("exact",0,36582,688,"176.62"),("xor",0,33180,670,"188.77"),
                                  ("exact",2,36582,688,"1,849.81"),("xor",2,33180,670,"1,829.36")]:
    x=transport[f"1024/{name}/{delay}"]
    assert x["two_way"]==byte and x["round_trips"]==rpc and f"{x['times']['query_ns']['median']/1e6:,.2f}"==timing and timing in text
scores=read(R/"agent_benchmark/results.json")
assert scores["n"]==57 and scores["match1"]["true"]==scores["match1"]["flat"]==44
r=read(R/"real_sessions/results.json")["all"]["all"]["metrics"]
assert r["cold"]["reads"]-r["selective"]["reads"]==239 and r["selective"]["snapshot"]*2==10348
rr=read(R.parent/"graph_memory_round58/checkpoint_value/results.json")["groups"]["original/long"]
assert rr["lo"]==rr["hi"]==33439 and rr["demand1024_body"]==30078
record=dict(pages=len(words),page_words=words,fonts=len(fonts),figures=2,tables=2,references=6,
            pdf_sha256=hashlib.sha256((HERE/"paper.pdf").read_bytes()).hexdigest(),
            evidence_files=["holdout/results.json","reference_audit/results.json","references/results.json",
                            "fast_path/results.json","transport/results.json","agent_benchmark/results.json",
                            "real_sessions/results.json","../graph_memory_round58/checkpoint_value/results.json"])
dest=HERE/"verification.json"
if "--record" in sys.argv:
    dest.write_text(json.dumps(record,indent=2)+"\n",encoding="utf8")
else:
    assert read(dest)==record
print("Verified",record["pages"],"pages and",len(record["evidence_files"]),"measurement sources.")
