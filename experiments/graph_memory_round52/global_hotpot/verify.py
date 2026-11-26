"""Replay choices from sealed native tables and scoring from archived support on CPU."""
import argparse
import hashlib
import sys
from grade import D, S, read, save, sha, evaluate
from surface import main as surface_check
CONF=D.parent/"global_confirm"
def check(export=False):
    sys.path.insert(0,str(CONF))
    from syntax import ARMS,choose
    seal=read(D/"prediction-seal.json")
    if export:
        from base64 import b64encode
        data={filename:b64encode((S/filename).read_bytes()).decode() for filename in ("seed.tsv","second.tsv","policy52-direct.tsv")}
        save(D/"native-outputs.json.gz",data)
    from base64 import b64decode
    native={k:b64decode(v,validate=True) for k,v in read(D/"native-outputs.json.gz").items()}
    assert set(native)=={"seed.tsv","second.tsv","policy52-direct.tsv"}
    tables={}
    for name,b in native.items():
        assert hashlib.sha256(b).hexdigest()==seal["cache"][name]
        tables[name]={q:list(map(int,tail)) for q,*tail in [l.split("\t") for l in b.decode("ascii").splitlines()]}
    roster=read(D/"roster.json");model=read(CONF/"dev-model.json");questions=read(D/"questions.json.gz");pred=read(D/"predictions.json.gz");names=read(D/"chosen-titles.json.gz")
    assert sha(CONF/"dev-model.json")==roster["learned_model"] and sha(CONF/"syntax.py")==roster["syntax"]
    assert read(D.parents[1]/"graph_memory_round31/support_pairs/source.json")["parquet_sha"]==roster["source"]
    assert sha(D/"questions.json.gz")==roster["questions"]
    assert roster["order"]==sorted(questions,key=lambda q:hashlib.sha256(("r52-hotpot-global-v1|"+q).encode()).digest())
    assert all(set(questions)==set(v) for v in tables.values())
    for q,question in questions.items():
        seed,free,plain,_,_,_,text,href,*_=tables["second.tsv"][q]
        assert seed==tables["seed.tsv"][q][0]==tables["policy52-direct.tsv"][q][0]
        gate=tables["policy52-direct.tsv"][q][8:14]
        addrs,conj,trained=choose(question,names[str(seed)][1],gate,plain,href,text,free,model)
        assert dict(seed=seed,choices=addrs,direct_gate=gate,coordination=conj,learned_direct=trained)==pred[q]
    assert ARMS==seal["arms"]
    evaluate();surface_check();print("VERIFIED 12800 choices, paired intervals and post-outcome sensitivity.")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--export",action="store_true");check(p.parse_args().export)
