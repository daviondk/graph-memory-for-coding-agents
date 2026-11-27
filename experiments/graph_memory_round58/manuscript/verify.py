"""Verify source metrics and the four-page ICDE format against local records."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
import fitz

HERE=Path(__file__).resolve().parent
R58=HERE.parent
R57=R58.parent/"graph_memory_round57"


def load(path):
    return json.loads(path.read_bytes())


def inspect():
    tex=(HERE/"paper.tex").read_text("utf8")
    with fitz.open(HERE/"paper.pdf") as doc:
        assert len(doc)==4 and all(tuple(p.rect)==(0,0,612,792) for p in doc)
        words=[len(p.get_text().split()) for p in doc]
        assert min(words)>400
        fids={f[0] for p in doc for f in p.get_fonts(full=True)}
        assert all(doc.extract_font(i)[-1] for i in fids)
        text="\n".join(p.get_text() for p in doc)
        assert "??" not in text
        assert all(f"Fig. {i}." in text for i in (1,2,3))
        assert len(re.findall(r"(?m)^TABLE I{1,2}$",text))==2
        assert set(re.findall(r"(?m)^\[(\d+)\]",text.split("REFERENCES")[-1]))==set(map(str,range(1,9)))
        for p in doc:
            assert all(34<b[1] and b[3]<756 for b in p.get_text("blocks"))
    restart=load(R58/"restart/results.json")
    inspect_methods=("cold","recent1024","largest1024","demand1024","recent4096","largest4096","demand4096","full")
    numbers=[]
    for panel,costs,queries in (("long",[106781,106186,88562,82907,93263,62827,61672,69607],196),
                                ("B",[34309,19358,18105,18063,53808,53808,53808,12168],492)):
        for k,n in zip(inspect_methods,costs):
            r=restart[panel+"-"+k]
            assert r["charged_bytes"]==n and r["post_n"]==queries
        numbers+=costs
    for k,read,full in (("cold",38.62,2.400),("recent1024",38.07,2.388),("largest1024",36.91,2.404),
                        ("demand1024",35.82,2.407),("full",27.69,2.381)):
        row=restart["long-"+k]
        assert round(row["post_read_ns"][0]/1e6,2)==read
        assert round(row["end_to_end_ns"][0]/1e9,3)==full
    audits=load(R58/"restart/audit.json")
    assert len(audits["projects"])==9 and audits["fallback"]["checked_rankings"]==24
    ext=load(R58/"restart_transfer/results.json")
    for panel,n,costs in (("long",189,{"demand1024":37640,"recent1024":42103,"largest1024":37944,"cold":30987}),
                          ("B",2063,{"demand1024":151189,"recent1024":202250,"cold":335947,"full":131923})):
        arms=ext[panel]["both"]["arms"]
        for method,c in costs.items():
            assert arms[method]["charged"]==c and arms[method]["post"]==n
            numbers.append(c)
    transfer=load(R58/"restart_transfer/audit.json")
    assert len(transfer)==12 and sum(r[p]["checked_sqlite_ranks"] for r in transfer.values() for p in r)==32632
    bound=load(R58/"checkpoint_value/results.json")["groups"]["original/long"]
    assert bound["lo"]==bound["hi"]==33439 and bound["demand1024_body"]==30078 and bound["demand1024_posting"]==0
    numbers.extend([33439,30078])
    natural=load(R58/"restart_transfer/no-padding.json")["aggregate"]
    for panel, methods in (("external-long",{"demand1024":32566,"recent1024":37031,"largest1024":32878}),
                           ("external-B",{"demand1024":146115})):
        for name,cost in methods.items():
            assert natural[panel][name]["charged"]==cost
            numbers.append(cost)
    solver=load(R58/"solver/results.json")
    assert solver["tasks"]==21 and [solver["arms"][k]["all_pass"] for k in ("adaptive","static","review","masked")]==[7,7,8,8]
    assert [solver["arms"][k]["passed_examples"] for k in ("adaptive","static")]==[46,46]
    assert sum(v["unique"] for v in solver["computed_cost"].values())==87
    rep=load(R57/"replication/results.json")
    assert rep["n"]==932 and round((1-rep["pooled"]["fill6_norm"]["bytes"]/rep["pooled"]["own_norm"]["bytes"])*100,1)==33.1
    warm=load(R57/"composed/results.json")
    for mode,m,s in (("continuous","own",123058),("continuous","shared",21142),("restart","shared",106781)):
        q=warm["long-"+mode+"-"+m]
        assert q["footprint"]==323584 and q["all_body_bytes"]+q["all_posting_bytes"]==s
    for s in set([f"{n:,}" for n in numbers]+["323,584","25,824","16,512","32,632","7/21","46/85","4,096","33.1"]):
        assert s in tex and s in text,s
    assets=("paper.tex","sources.bib","paper.pdf","capture.py","retention.pdf","pair-worlds.pdf","restart-screen.png")
    return dict(pages=len(words),page_words=words,format_pt=[612,792],embedded_fonts=len(fids),
                figures=3,tables=2,references=8,unresolved_references=0,
                sha256={n:sha256((HERE/n).read_bytes()).hexdigest() for n in assets})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--record",action="store_true");args=p.parse_args()
    record=inspect();out=HERE/"verification.json"
    if args.record:
        out.write_bytes((json.dumps(record,indent=2,sort_keys=True)+"\n").encode())
    else:
        assert load(out)==record
    print("Verified four IEEE pages, three figures, two tables, eight references, query costs and end-to-end timings.")
