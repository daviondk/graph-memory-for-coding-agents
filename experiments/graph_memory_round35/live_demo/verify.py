"""Verify the offline demo and native and browser-audit receipts."""
import argparse,gzip,json,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    cli=argparse.ArgumentParser();cli.add_argument("--seal",action="store_true");a=cli.parse_args()
    markup=(D/"index.html").read_text(encoding="utf8")
    payload=json.loads(markup.split('<script id="dataset" type="application/json">')[1].split('</script>')[0])
    assert len(payload["weights"])==16 and payload["counts"]=={"win":43,"loss":16,"tie":390} and len(payload["cases"])==3
    src=read(D/"source.json");ref=read(D/"oracle-receipt.json");ev=read(D/"event-oracle.json");br=read(D/"browser-receipt.json")
    assert src["html"]==br["html"]==sha(D/"index.html")
    assert src["program"]==sha(D/"build.py") and src["protocol"]==sha(D/"PROTOCOL_RU.md")
    assert ref["source"]==ev["source"]==sha(D/"source.json")
    assert ref["program"]==sha(D/"oracle.py") and ev["code"]==sha(D/"event_oracle.py") and br["program"]==sha(D/"browser_check.mjs")
    assert ref["oracle"]==br["oracle"]==sha(D/"ui-oracle.json")
    assert br["states"]==ref["query_cut_policy"]==24 and br["remote_requests"]==0 and br["errors"]==[]
    assert ev["prefixes"]==br["native_per_event_prefixes"]==161 and br["event_lists"]==24
    assert {k:sha(D/"qa"/k) for k in br["screenshots"]}==br["screenshots"]
    scores=read(D/"ui-oracle.json")
    for c in payload["cases"]:
        assert set(c["cuts"])==set(scores[c["q"]])==set(ev["states"][c["q"]]["cuts"])=={"25","50","75","100"}
        for pct,s in c["cuts"].items():
            for mode in ("added_events","removed_events"):
                picked=s[mode];receipt=ev["states"][c["q"]]["cuts"][pct][mode]
                assert receipt["count"]==len(picked) and receipt["first"]==picked[:60]
                assert receipt["sha"]==hashlib.sha256(json.dumps(picked,separators=(",",":")).encode()).hexdigest()
        r=scores[c["q"]]["50"];diff=int(r["exact"]["full"])-int(r["append"]["full"]);assert diff=={"win":1,"loss":-1,"tie":0}[c["kind"]]
    dest=D/"manifest.json";files={p.relative_to(D).as_posix():sha(p) for p in D.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p!=dest}
    if a.seal and not dest.exists():dest.write_text(json.dumps(files,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    assert files==read(dest)
    print(f"Verified 24 retrieval states, 24 event tables, 161 native output graphs and {len(files)} artifacts.",sha(dest))
if __name__=="__main__":main()
