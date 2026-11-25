from contextlib import closing
import json
from store import ROOT,connect,cases,view,FORMATS,POLICIES
with closing(connect()) as db:
    rows=cases(db)
    all_views={r["id"]:{f+"|"+p:view(db,r["id"],f,p) for f in FORMATS for p in POLICIES} for r in rows}
payload=json.dumps({"cases":rows,"views":all_views},ensure_ascii=False,separators=(",",":")).replace("<","\\u003c")
page=(ROOT/"index.html").read_text(encoding="utf8")
tag='<script type="application/json" id="snapshot">null</script>'
assert page.count(tag)==1
(ROOT/"inspection.html").write_text(page.replace(tag,tag.replace(">null<",">"+payload+"<")),encoding="utf8")
print(len(rows),sum(map(len,all_views.values())))
