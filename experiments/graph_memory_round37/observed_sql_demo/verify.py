"""Verify portable artifact digests and preservation of the original SQL operator."""
from pathlib import Path
from hashlib import sha256
import argparse,json
D=Path(__file__).resolve().parent
FILES=("eager.db","inverse.db","serve.py","index.html","style.css","app.js","build.py","selftest.py",
       "browser_check.py","verify.py","REPORT_RU.md","REPRODUCE_RU.md","source.json","test-oracle.json",
       "checks.json","browser.json","qa/desktop.png","qa/capacity.png","qa/mobile.png",
       "operators/code_store/storage.py","operators/code_store/inputs.py","operators/range_read/query.py")
def sha(p):return sha256(p.read_bytes()).hexdigest()
def load(name):return json.loads((D/name).read_bytes())
def main(seal):
    values={n:sha(D/n) for n in FILES};from_source=load("source.json")
    for path,expected in from_source["sources"].items():
        local="operators/"+path
        if local in values:assert values[local]==expected
    boxes=load("checks.json")
    assert boxes["databases_sha256"]==[values[n] for n in ("eager.db","inverse.db")]
    assert boxes["ranges"]==709
    tested=load("browser.json");assert not tested["js_errors"] and not tested["blocked_external_requests"]
    assert all(values["qa/"+n]==h for n,h in tested["screenshot_sha"].items())
    assert not any(D.glob("*.db-*"))
    if seal:(D/"manifest.json").write_text(json.dumps(values,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    assert load("manifest.json")==values
    print("OK",len(values),"files; manifest",sha(D/"manifest.json"))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");main(p.parse_args().seal)
