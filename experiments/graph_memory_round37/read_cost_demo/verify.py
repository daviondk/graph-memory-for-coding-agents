from pathlib import Path
from collections import Counter
import re,hashlib,json,sys
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    s=read(D/"source.json");r=read(D/"browser-receipt.json");assert s["html"]==r["html"]==sha(D/"index.html") and s["template"]==sha(D/"template.html") and s["build"]==sha(D/"build.py") and r["program"]==sha(D/"browser_check.py");expected=read(D/"oracle.json");assert s["oracle"]==r["oracle"]==sha(D/"oracle.json")
    html=(D/"index.html").read_text(encoding="utf8");raw=re.search(r'<script id="caseData" type="application/json">(.*?)</script>',html,re.S);cases=json.loads(raw[1]);assert len(cases)==2 and not re.search(r'<(?:script|link|img)[^>]+(?:src|href)\s*=\s*"https?://',html)
    count=0
    for cs in cases:
        for m,order in enumerate(cs["orders"]):
            assert len(order)==len(set(order))==20
            for depth in range(21):
                g=Counter();a=Counter();cost=0
                for j in order[:depth]:
                    u=cs["items"][str(j)];g.update(u["g"]);a.update(u["a"]);cost+=u["cost"]
                hit=[g[i]>=need for i,need in enumerate(cs["groups"])];complete=all(hit) or any(a[i]>=need for i,need in enumerate(cs["alts"]));v={"groups":hit,"complete":complete,"spent":cost};assert v==expected[str(cs["id"])][m][depth];count+=1
    assert count==84 and r["threshold_depth_combinations"]==9200 and len(r["ui_states"])==11 and not r["remote_requests"] and not r["page_errors"] and r["offline"] and r["mobile_widths_checked"]==[390,320]
    for name,h in r["screenshots"].items():assert sha(D/"qa"/name)==h
    p=D/"manifest.json";items={q.relative_to(D).as_posix():sha(q) for q in sorted(D.rglob("*")) if q.is_file() and q!=p and "__pycache__" not in q.parts}
    if "--seal" in sys.argv:p.write_text(json.dumps({"algorithm":"SHA-256","files":items},sort_keys=True,indent=2)+"\n",encoding="utf8")
    assert read(p)["files"]==items;print("Verified",count,"prefixes,",len(items),"files,",sha(p))
if __name__=="__main__":main()
