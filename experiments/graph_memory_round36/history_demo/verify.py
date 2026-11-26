import argparse,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(p.read_bytes())
def main():
    cli=argparse.ArgumentParser();cli.add_argument("--seal",action="store_true");a=cli.parse_args()
    src=get(D/"source.json");r=get(D/"oracle-receipt.json");br=get(D/"browser-receipt.json")
    assert sha(D/"index.html")==src["html"]==br["html"] and sha(D/"build.py")==src["program"]
    assert r["source"]==sha(D/"source.json") and r["code"]==sha(D/"oracle.py")
    assert r["oracle"]==br["oracle"]==sha(D/"ui-oracle.json") and br["code"]==sha(D/"browser_check.mjs")
    assert br["states"]==r["policy_states"]==36 and br["edge_checks"]==108 and r["output_prefixes"]==98 and r["full_prefixes"]==12
    assert br["remote_requests"]==0 and not br["errors"] and all(sha(D/"qa"/k)==v for k,v in br["screenshots"].items())
    raw=get(D/"ui-oracle.json");assert len(raw)==3 and all(len(t)==4 for t in raw.values())
    fields=sorted(tuple(v["50"]["modes"][m]["full"] for m in ("E","M","L")) for v in raw.values())
    assert fields==sorted([(True,True,False),(True,False,False),(True,False,True)])
    target=D/"manifest.json";fs={f.relative_to(D).as_posix():sha(f) for f in D.rglob("*") if f.is_file() and f!=target and "__pycache__" not in f.parts}
    if a.seal and not target.exists():target.write_text(json.dumps(fs,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    assert fs==get(target);print("Verified 36 policy states and 108 browser edge tables.",sha(target))
if __name__=="__main__":main()
