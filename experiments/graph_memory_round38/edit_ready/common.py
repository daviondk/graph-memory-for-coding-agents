from pathlib import Path
from collections import Counter,defaultdict
from hashlib import sha256
import json,gzip
D=Path(__file__).resolve().parent
ROOT=D.parents[1]
R37=ROOT/"graph_memory_round37"
def h(s):return sha256(s.encode("utf8")).hexdigest()
def sha(p):return sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,x):
    data=(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(data,compresslevel=5,mtime=0) if p.suffix==".gz" else data)
    return sha(p)
def open_r37():
    sources=[(R37/"code_visibility/events.json.gz","b4527e3337e2d567495d4836f440b56cb59605dec84dfff6cb0368c6924c7449"),(R37/"edit_demand/native_boundaries.json.gz","bd21269212e38ddd970acb7c4a528360bed10b0826c6f7081ef4000d2762bdae")]
    assert all(sha(p)==s for p,s in sources)
    return tuple(get(p) for p,s in sources)
def timeline(corpus,bound):
    result={}; candidates={};count=defaultdict(Counter); signed_reads={}
    for rid,v in corpus.items():
        group="main" if v["subset"] in ("main_takeovers","predecessors") else "additional"
        z=count[group];z["runs"]+=1
        ev=v["events"]+[[a+.5,"gap"] for a,b in bound[rid].get("gaps",[])]
        ev.sort(key=lambda x:x[0]); window=[]; seen=set(); selected={}; reads={}; cand={}
        receipts={u[0]:(u[1],u[2],u[3]) for u in bound[rid].get("successful_writes",[]) if u[2]=="str_replace"}
        for k,e in enumerate(ev):
            at,kind,*t=e
            if kind in ("barrier","gap"):
                window=[];seen.clear();continue
            path=t[0];address=h(path)
            if kind=="read":
                if t[2]:
                    seen.add(address);reads[at]=(path,t[1],t[2]);window.append([at,"view",address])
                continue
            if kind=="write_start":
                z["write_starts"]+=1
                pair=receipts.get(at)
                if pair:
                    z["linked_replacements"]+=1
                    if address in seen:
                        end=pair[0]
                        intr=[y for y in ev[k+1:] if y[0]<end and (y[1] in ("barrier","gap") or len(y)>2 and h(y[2])==address and y[1] in ("write_start","edit","other"))]
                        if not intr:
                            assert pair[2]==address
                            z["structural_candidates"]+=1
                            for j,x in enumerate(window):selected[x[0]]=x
                            selected[at]=[at,"snapshot+invalidate",address];cand[at]=(end,address)
                if at not in selected:
                    window.append([at,"invalidate",address])
                else:window.append(selected[at])
            else:
                window.append([at,"invalidate",address])
            seen.discard(address)
        # Restart at each barrier: a sentinel before the first view of every selected clean window.
        reset_times=[e[0] for e in ev if e[1] in ("gap","barrier")]
        selected.update({t:[t,"reset"] for t in reset_times if selected})
        if cand:
            result[rid]=dict(events=sorted(selected.values()),issue=v["issue"],repo=v["repo"],group=group)
            candidates[rid]=cand
            signed_reads[rid]={at:reads[at] for at,e in selected.items() if e[1]=="view"}
    return result,candidates,signed_reads,count
