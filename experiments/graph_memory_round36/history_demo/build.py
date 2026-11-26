"""Reuse the signed two-policy projection and extend it with the once-visible edge set."""
import importlib.util,json,hashlib,sys
from pathlib import Path
from collections import defaultdict
D=Path(__file__).resolve().parent;W=D.parents[1];R35=W/"graph_memory_round35/live_demo";M=D.parent/"materialized_append"
spec=importlib.util.spec_from_file_location("r35_demo_export",R35/"build.py");base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
l=base.l
def pick():
    states=l.read(M/"outcomes.json.gz");groups=defaultdict(list)
    rules={(1,1,0):"win",(1,0,0):"loss",(1,0,1):"tie"};by={}
    for f in states:
        if f["cut"]==50 and f["eligible"] and not f["pilot"]:
            group=rules.get(tuple(f["arms"][m][0] for m in ("E","M","L")))
            if group:groups[group].append(f["q"]);by[f["q"]]=f["t"]
    shards={q:sh for sh in range(8) for q,*_ in l.read(M/f"orders-{sh}.json.gz")};out={};ts=set()
    for group in ("win","loss","tie"):
        q=next(q for q in sorted(groups[group],key=lambda q:base.h("R36-history-demo/"+q)) if by[q] not in ts)
        ts.add(by[q]);out[q]=(shards[q],by[q],group)
    return out,{k:len(v) for k,v in groups.items()},None
def main():
    sealed=l.read(R35/"manifest.json");assert sealed["build.py"]==l.sha(R35/"build.py")
    base.D=D;base.pick=pick;base.main()
    html=(D/"index.html").read_text(encoding="utf8");tag='<script id="dataset" type="application/json">';raw=html.split(tag)[1].split('</script>')[0];doc=json.loads(raw)
    for c in doc["cases"]:
        ever=set()
        for k in ("25","50","75","100"):
            st=c["cuts"][k];ever.update(tuple(z[:3]) for z in st["added_events"]);stale=set(map(tuple,st["stale"]))
            st["once"]=sorted(ever&stale);st["never"]=sorted(stale-ever);assert len(st["once"])==st["stale_visible"]
    text=html.replace(tag+raw+'</script>',tag+json.dumps(doc,ensure_ascii=False,separators=(",",":"))+'</script>')
    (D/"index.html").write_text(text,encoding="utf8",newline="\n")
    meta=l.read(D/"source.json");meta.update({"r35":l.sha(R35/"manifest.json"),"r36":l.sha(M/"manifest.json"),"program":l.sha(D/"build.py"),"html":l.sha(D/"index.html")});l.save(D/"source.json",meta)
if __name__=="__main__":main()
