"""Verify frozen outputs and the development-only selection from recorded scorings."""
import json,gzip,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=="__main__":
    manifest=load(D/"manifest.json")
    for file,h in manifest.items():assert sha(D/file)==h,file
    dev=load(D/"dev-selection.json");assert dev["metrics"]==sha(D/"dev-metrics.json") and dev["models"]==sha(D/"models.json")
    for k in ("dev","test"):
        seal=load(D/(k+"-seal.json"));assert seal["rank"]==sha(D/(k+"-ranks.json.gz"));metrics=load(D/(k+"-metrics.json"))
        assert metrics["outcomes"]==sha(D/(k+"-outcomes.json.gz"))
    oracle=load(D/"dev-oracle.json");assert oracle["n"]==sum(oracle["hits_at_n_gridpoints"].values())
    sec=D/"seed_transfer";late=load(sec/"results.json");assert late["seal"]==sha(sec/"seal.json") and late["outcomes"]==sha(sec/"outcomes.json.gz")
    print(f"Verified {len(manifest)} frozen files, dev580, test2000 and four held-out training seeds.")