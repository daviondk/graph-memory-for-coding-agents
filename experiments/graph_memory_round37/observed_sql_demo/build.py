"""Build portable demo SQLite files from three already published experiment transitions."""
from pathlib import Path
from hashlib import sha256
import sys,gzip,json,tempfile,shutil
D=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(D/"operators/range_read"))
import query
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf-8")
PICKS=[
 ("growth","21b4cd4a37de5272a02a0774d7f2ce830dd9583cead429b85415c5ca383723f1"),
 ("contraction","e46442c05a2d35c6e3cc7b9446a383b239dc85c0a83b60f17601413d29d7b5d5"),
 ("capacity","9bbf5e9d167d8f72864ffca888afbbfbb75ab23fb4eb0181c62392c9bb0dfe6c")]
def main():
    src=D.parent;rg=src/"range_read";store=src/"code_store";vis=src/"code_visibility"
    paths=[store/"prefix_inputs.json.gz",store/"reference.json.gz",rg/"forecasts.json.gz",vis/"observations.json.gz",
           rg/"query.py",store/"storage.py",store/"inputs.py"]
    for p in paths:
        assert sha(p)==load(p.parent/"manifest.json")["files"][p.name]
    for p in paths[-3:]:assert sha(p)==sha(D/"operators"/p.parent.name/p.name)
    inputs,ref,panel,observed=map(load,paths[:4])
    cases={}; fixtures={}; prepared={}
    for e,(key,q) in enumerate(PICKS,1):
        it=inputs[q]; rr=panel[q]; expected=ref[q]; obs=observed[q]["observed"]
        base={n:bytes.fromhex(s) for n,s in it["base"]}; receipt={n:bytes.fromhex(s) for n,s in it["receipt"]}
        k,z,d=it["start"],it["end"],it["delta"]
        possible=set(receipt)|{n if n<k else n+d for n in base if n<k or n>z}
        kept={n for n,_ in expected};dropped=sorted(possible-kept)
        default=rr["range"];assert default==[min(x[0] for x in obs),max(x[0] for x in obs)]
        special=[dropped[0],dropped[0]] if dropped else [k,max(k,z+d)]
        cases[key]=dict(id=e,label=key,issue=it["issue"],zone=it["zone"],path=it["path"],
                        path_id=sha256(it["path"].encode()).hexdigest(),episode=q,
                        requested=default,special=special)
        prepared[e]=dict(it,base=list(base.items()),receipt=receipt)
        fixtures[key]=dict(oracle=expected,default=rr["arms"],retention_omissions=dropped,
                           actual_observed=len(obs),source_q=q)
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        folder=Path(tmp);files=[folder/"eager.db",folder/"inverse.db"]
        conns=query.build(files,prepared)
        try:
            lazy=conns[1];lazy.execute("CREATE TABLE demo(k TEXT PRIMARY KEY, case_json TEXT) WITHOUT ROWID")
            lazy.executemany("INSERT INTO demo VALUES (?,?)",[(key,json.dumps(cases[key],sort_keys=True)) for key in cases])
            for c in conns:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
                assert c.execute("PRAGMA journal_mode=DELETE").fetchone()==("delete",)
                assert c.execute("PRAGMA integrity_check").fetchone()==("ok",)
        finally:
            for c in conns:c.close()
        for p in files:shutil.copyfile(p,D/p.name)
    write(D/"test-oracle.json",fixtures)
    write(D/"source.json",dict(sources={str(p.relative_to(src)).replace(chr(92),"/"):sha(p) for p in paths},
            selected=dict(PICKS),selection="Purposive positive/negative line delta with returned receipt and carried addresses; actual evictions in third case.",
            native_operator=sha(rg/"query.py"),sqlite=__import__("sqlite3").sqlite_version))
if __name__=="__main__":main()
