"""Build a read-only exhibition dataset, omitting all code and all prompt text."""
from pathlib import Path
from contextlib import closing
import hashlib,sqlite3,gzip,json,os,tempfile
from tokenizers import Tokenizer

ROOT=Path(__file__).resolve().parent
STUDY=ROOT.parent/"handoff_ranges"
EARLIER=ROOT.parents[1]/"graph_memory_round31/natural_handoff"
PREFIX=Path("D:/CodexResearch/x20-r31-handoff/prefix.json.gz")
TOKEN=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def read(path):
    raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf8")

def main():
    lock=read(STUDY/"seal.json")
    assert digest(PREFIX.read_bytes())==lock["prefix"] and digest(TOKEN.read_bytes())==lock["tokenizer"]
    for parent in [STUDY,EARLIER]:
        manifest=read(parent/"manifest.json")
        if "files" in manifest:manifest={r["file"]:r["sha"] for r in manifest["files"]}
        for name in (["packets.json.gz","targets.json.gz","outcomes.json.gz"] if parent==STUDY else ["delivery-metadata.json.gz"]):
            assert manifest[name]==digest((parent/name).read_bytes())
    targets=read(STUDY/"targets.json.gz");packets=read(STUDY/"packets.json.gz")
    cases=[r for r in read(STUDY/"outcomes.json.gz") if r["scope"]=="main_takeovers" and r["split"]=="test"]
    assert len(cases)==171 and len({r["issue"] for r in cases})==25
    metadata={r["group"]:r for r in read(EARLIER/"delivery-metadata.json.gz") if r["view"]=="repo_only"}
    snapshots={r["cp"] for r in cases}
    tokenizer=Tokenizer.from_file(str(TOKEN));tokenizer.no_truncation()
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        tmp=Path(temp)/"store.sqlite"
        with closing(sqlite3.connect(tmp)) as db:
            db.executescript("""
            create table cases(g text primary key, issue text, cp text, target_path text, target_json text, address_wp integer, routed integer) without rowid;
            create table observations(cp text, idx integer, path text, step integer, revision text, line_count integer, first integer, last integer, primary key(cp,idx)) without rowid;
            create table lines(cp text,idx integer,ord integer,line_no integer,fp text,wp integer,primary key(cp,idx,ord)) without rowid;
            create index versions_by_path on observations(cp,path,idx);
            create table catalog(cp text,path text,idx integer,primary key(cp,path)) without rowid;
            """)
            for r in cases:
                cp=r["cp"]; t=targets[metadata[r["group"]]["q"]];route=packets[cp]["routes"].get(t["path"],{}).get("one_wide")
                db.execute("insert into cases values(?,?,?,?,?,?,?)",(r["group"],r["issue"],cp,t["path"],json.dumps([*t["ends"],*t["inner"]]),packets[cp]["address_tokens"]["one_wide"],route))
            for row in read(PREFIX):
                cp=row["cp"]
                if cp not in snapshots:continue
                for path,routes in packets[cp]["routes"].items():
                    if "one_wide" in routes:db.execute("insert into catalog values(?,?,?)",(cp,path,routes["one_wide"]))
                for event in row["events"]:
                    lines=event["lines"]
                    if not lines:continue
                    idx=event["idx"];path=event["path"]
                    ids=[(ln,digest(text.encode())) for ln,text in lines]
                    version=digest(json.dumps(ids,separators=(",",":")).encode())
                    items=[f"[{path}:{ln}] {text}" for ln,text in lines]
                    prices=[len(encoded.ids) for encoded in tokenizer.encode_batch(items,add_special_tokens=False)]
                    db.execute("insert into observations values(?,?,?,?,?,?,?,?)",(cp,idx,path,event["step"],version,len(lines),lines[0][0],lines[-1][0]))
                    db.executemany("insert into lines values(?,?,?,?,?,?)",[(cp,idx,i,ln,fp,prices[i]) for i,(ln,fp) in enumerate(ids)])
            assert db.execute("pragma integrity_check").fetchone()==("ok",)
            db.commit();db.execute("vacuum")
            counts={t:db.execute("select count(*) from "+t).fetchone()[0] for t in ("cases","observations","lines","catalog")}
        destination=ROOT/"handoff.sqlite"
        if destination.exists():
            assert destination.read_bytes()==tmp.read_bytes(),"Existing store differs"
        else:
            os.replace(tmp,destination)
    save(ROOT/"build.json",{"store":digest(destination.read_bytes()),"bytes":destination.stat().st_size,"counts":counts,"checkpoints":len(snapshots),"source":lock["prefix"],"study":digest((STUDY/"manifest.json").read_bytes()),"tokenizer":lock["tokenizer"]})
    print(counts)
if __name__=="__main__":main()
