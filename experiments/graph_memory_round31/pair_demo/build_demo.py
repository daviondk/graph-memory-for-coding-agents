"""Create a portable reference panel, tiny SQLite store, and standalone viewer."""
import hashlib,json,sqlite3,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PAIR=HERE.parent/"support_pairs";sys.path.insert(0,str(PAIR))
from prepare import PRIVATE,get,put,sha
def main():
    src=get(PAIR/"source.json");ranks=get(PAIR/"rankings.json.gz");data=get(PRIVATE/"blind.json.gz");labs=get(PRIVATE/"labels.json.gz")
    assert sha(PRIVATE/"blind.json.gz")==src["observations"] and sha(PRIVATE/"labels.json.gz")==src["labels"]
    saved=get(PAIR/"cache-measurements.json.gz")
    panel=sorted(ranks,key=lambda q:hashlib.sha256(("r31-demo-v1/"+q).encode()).digest())[:24]
    rows=[]
    for q in panel:
        r=ranks[q];c=data[q];titles=[c["titles"][i] for i in r["order"]];e=r["pairs"]["joint"]
        selection=saved[q]["joint"]["2"]["tree"];pairs=[(a<<4)|b for a,b in e]
        rows.append({"q":q,"question":c["q"],"titles":titles,"full":pairs,"tree":[pairs[i] for i in selection],"raw":pairs[:6],
                     "gold":[i for i,t in enumerate(titles) if t in labs[q]["support"]]})
    content={"corpus":"HotpotQA distractor dev","questions":rows}
    put(HERE/"cases.json",content)
    target=HERE/"evidence.sqlite"
    if not target.exists():
        with sqlite3.connect(target) as db:
            db.execute("create table pairs(q text primary key, n integer not null, full blob not null, tree blob not null, raw blob not null) without rowid")
            db.executemany("insert into pairs values(?,?,?,?,?)",((r["q"],len(r["titles"]),bytes(r["full"]),bytes(r["tree"]),bytes(r["raw"])) for r in rows));db.commit();db.execute("vacuum")
    with sqlite3.connect(target.as_uri()+"?mode=ro",uri=True) as db:
        assert db.execute("pragma integrity_check").fetchone()==("ok",)
        assert all(db.execute("select n,full,tree,raw from pairs where q=?",(r["q"],)).fetchone()==(len(r["titles"]),bytes(r["full"]),bytes(r["tree"]),bytes(r["raw"])) for r in rows)
    template=(HERE/"viewer.html").read_text(encoding="utf8")
    payload=json.dumps(content,separators=(",",":"),ensure_ascii=False).replace("<","\\u003c")
    (HERE/"evidence.html").write_text(template.replace("/*__CASES__*/null",payload),encoding="utf8")
    put(HERE/"build.json",{"panel":panel,"ranks":sha(PAIR/"rankings.json.gz"),"evidence":sha(HERE/"cases.json"),"db":sha(target),"html":sha(HERE/"evidence.html")})
if __name__=="__main__":main()
