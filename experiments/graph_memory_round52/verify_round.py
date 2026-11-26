"""Check local artifact integrity and the numerical claims shared between reports."""
from pathlib import Path
from hashlib import file_digest
import gzip
import json
import sys

D=Path(__file__).resolve().parent

def data(name):
    path=D/name
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def digest(path):
    with path.open("rb") as f:return file_digest(f,"sha256").hexdigest()
def files():
    return sorted(p for p in D.rglob("*") if p.is_file() and "__pycache__" not in p.parts and
                  p.name!="round-manifest.json" and not any(x.startswith("tmp") for x in p.relative_to(D).parts))

def main():
    if "--seal" in sys.argv:
        all_hashes={p.relative_to(D).as_posix():digest(p) for p in files()}
        (D/"round-manifest.json").write_text(json.dumps(all_hashes,indent=2,sort_keys=True)+"\n",encoding="utf8")
    receipt=data("round-manifest.json");assert set(receipt)=={p.relative_to(D).as_posix() for p in files()}
    for n,v in receipt.items():assert digest(D/n)==v,n
    g=data("global_titles/results.json");p=data("global_policy/results.json")
    assert p["n"]==g["n"]==12576 and g["first"]["common_first_hit"]==12325
    assert p["complete"]["primary_href"]-p["complete"]["primary_text"]==1340
    c=data("global_confirm/results.json")["train_confirm"];assert c["n"]==2400 and c["complete"]["learned_dev"]==1091
    a=data("global_confirm/large/results.json")["independent_12000"]
    assert a["n"]==12000 and a["complete"]["learned_dev"]==a["complete"]["dev_tree"]==a["complete"]["coord_or_same_as"]==5419
    assert a["contrasts"]["learned_dev vs coord_or_same_as"]["switched"]==0
    h=data("global_hotpot/results.json");assert h["n"]==1280 and h["contrasts"]["primary_href-primary_text"]["full"]["wins"]==51
    qa=data("global_answers/confirm/supplement/results.json")["fallback"]
    assert qa["n"]==512 and round(qa["paired"]["f1"]["delta_pp"],2)==2.57 and qa["paired"]["full"]["wins"]==48
    db=data("address_history/results.json")["plans"]
    assert len({r["digest"] for r in db.values()})==1 and db["address"]["reads"]==80314
    assert (db["address"]["rows"],db["journal"]["rows"])==(4592,5822)
    bundle=data("submission/verification.json")
    assert bundle["files"]==75 and bundle["pages"]==4 and bundle["seconds"]<300
    assert digest(D/"submission/candidate.zip")==bundle["sha256"]
    print(f"Verified {len(receipt)} research artifacts, ten serving consoles, and the reported paired outcomes.")
if __name__=="__main__":main()

