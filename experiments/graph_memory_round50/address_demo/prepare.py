"""Create a portable address-selection snapshot from previously sealed, local study artifacts."""
from pathlib import Path
import argparse,gzip,hashlib,json,sqlite3,struct
D=Path(__file__).resolve().parent
def h(data):return hashlib.sha256(data).hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--study",type=Path,default=D.parent/"gate_confirmation")
    parser.add_argument("--projection",type=Path,default=Path("D:/CodexResearch/x20-r50-gate-confirmation"))
    parser.add_argument("--output",type=Path,default=D/"address.sqlite");args=parser.parse_args()
    source=args.study;private=args.projection
    files=load(source/"manifest.json")["files"]
    def signed(name):
        p=source/name;assert h(p.read_bytes())==files[name],name;return load(p)
    def checked(name,expected):
        p=private/name;assert h(p.read_bytes())==expected,name;return load(p)
    project=signed("projection-seal.json");inp=signed("input-seal.json");ans=signed("answer-seal.json")
    assert h((source/"input-seal.json").read_bytes())==ans["input"]
    visible=checked("catalog-input.json.gz",project["visible"]);full=checked("visible.json.gz",project["source"])
    records=signed("catalog-receipts.json.gz");orders=signed("orders.json.gz")
    answers=signed("answers.json.gz");prompts=signed("prompts.json.gz");ctx=signed("contexts.json.gz");out=signed("outcomes.json.gz")
    gold=signed("gold.json.gz");threshold=signed("threshold-seal.json")["primary"]
    assert inp["contexts"]==files["contexts.json.gz"] and inp["prompts"]==files["prompts.json.gz"] and ans["answers"]==files["answers.json.gz"]
    assert signed("retrieval-seal.json")["orders"]==files["orders.json.gz"]
    assert set(orders)==set(ctx)==set(gold)==set(visible)==set(out)==set(records) and len(ctx)==1280
    assert set(answers)==set(prompts) and all(h(struct.pack(f"<{len(ts)}I",*ts))==k for k,ts in prompts.items())
    dest=args.output
    if dest.exists():raise FileExistsError("Choose a fresh output path to rebuild.")
    con=sqlite3.connect(dest)
    con.executescript("""
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
    CREATE TABLE episode (id TEXT PRIMARY KEY, question TEXT, first_title TEXT, snippet TEXT, first_id INT, label TEXT);
    CREATE TABLE candidate (episode TEXT, ordinal INT, rank INT, title TEXT, cosine REAL, mentioned INT, PRIMARY KEY(episode,rank)) WITHOUT ROWID;
    CREATE TABLE archived (episode TEXT, ordinal INT, snapshot TEXT, prompt_sha TEXT, input_tokens INT, f1 REAL, PRIMARY KEY(episode,ordinal)) WITHOUT ROWID;
    CREATE TABLE response (snapshot TEXT, prompt_sha TEXT, output TEXT, PRIMARY KEY(snapshot,prompt_sha)) WITHOUT ROWID;
    CREATE TABLE gold (episode TEXT PRIMARY KEY, aliases TEXT, supports TEXT) WITHOUT ROWID;
    CREATE INDEX episode_label ON episode(label,id);
    """)
    snapshot=h((source/"input-seal.json").read_bytes());tags=dict(snapshot=snapshot,manifest=h((source/"manifest.json").read_bytes()),model=ans["model"],threshold=repr(threshold),count="1280")
    con.executemany("INSERT INTO metadata VALUES(?,?)",sorted(tags.items()))
    con.executemany("INSERT INTO response VALUES(?,?,?)",[(snapshot,k,answers[k]["answer"]) for k in sorted(answers)])
    for q in sorted(ctx):
        key=h(q.encode())[:16];r=orders[q];c=ctx[q];obs=out[q]["arms"];rr=records[q]
        question,snippet,cats=visible[q];first=int(c["seed"]);docs=full[q][1]
        assert h(question.encode())==rr["question"] and h(snippet.encode())==rr["snippet"] and first==rr["first"]==r["seed"]
        titles=dict(cats);first_title=docs[first][1]
        assert h((first_title+"\0"+docs[first][2]).encode())==c["cluster"]
        winners=r["dense"],r["linked_dense"]
        assert r["order"][0]==winners[0] and next((i for i in r["order"] if i in r["edges"]),winners[0])==winners[1]
        a,b=winners;gap=r["scores"][str(a)]-r["scores"][str(b)]
        adaptive=b if gap<=threshold else a;assert adaptive==r["adaptive"]
        diff=obs["adaptive"][1]-obs["dense"][1]
        label="gain" if diff>0 else "loss" if diff<0 else "switched_tie" if adaptive!=a else "unchanged"
        con.execute("INSERT INTO episode VALUES(?,?,?,?,?,?)",(key,question,first_title,snippet,first,label))
        for rank,i in enumerate(r["order"],1):
            assert h(titles[i].encode())==rr["titles"][str(i)]
            con.execute("INSERT INTO candidate VALUES(?,?,?,?,?,?)",(key,i,rank,titles[i],r["scores"][str(i)],int(i in r["edges"])))
        unique={}
        for arm,(i,k,n) in c["refs"].items():
            assert k in prompts and len(prompts[k])==n==obs[arm][5] and i==r[arm]
            record=(key,i,snapshot,k,n,obs[arm][1]);assert unique.setdefault(i,record)==record
        con.executemany("INSERT INTO archived VALUES(?,?,?,?,?,?)",unique.values())
        aliases,hashes,support=gold[q]
        names=[first_title if i==first else titles[i] for i in range(len(hashes))]
        assert [h(z.encode()) for z in names]==hashes
        con.execute("INSERT INTO gold VALUES(?,?,?)",(key,json.dumps(aliases,ensure_ascii=False),json.dumps(sorted({t for t in names if h(t.encode()) in support}),ensure_ascii=False)))
    con.commit();assert con.execute("PRAGMA integrity_check").fetchone()==("ok",);con.close()
    print(h(dest.read_bytes()),dest.stat().st_size)
if __name__=="__main__":main()

