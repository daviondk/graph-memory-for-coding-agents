import re
from paths_href import *
def main():
    lock=get(D/"answer-seal.json");cache=set(get(D/"reuse.json.gz"));new=set(get(D/"answers.json.gz"))-cache
    req=[(k,"new") for k in sorted(new,key=lambda k:hexb(("r49-infer|"+k).encode()))]
    for group,label in [(cache,"repeat_cached"),(new,"repeat_new")]:
        req.extend((k,label) for k in sorted(group,key=lambda k:hexb(("r50-href-repeat|"+k).encode()))[:32])
    pattern=re.compile(r"print_timing: id\s+\d+ \| task (\d+) \|\s+(prompt eval|eval|total) time =\s+([\d.]+) ms /\s+(\d+) tokens?")
    times={}
    for line in (P/"server.stderr").read_text(encoding="utf8").splitlines():
        m=pattern.search(line)
        if m:
            i,kind,ms,n=m.groups();times.setdefault(int(i),{})[kind]=[float(ms),int(n)]
    assert lock["resumed"]==0 and len(times)==len(req)
    rows=[]
    for (k,label),v in zip(req,times.values(),strict=True):
        rows.append([k,label,*v["prompt eval"],*v["eval"],*v["total"]])
    put(D/"timing-events.json.gz",rows);put(D/"costs.json",dict(calls=len(rows),seconds=lock["seconds"],server_ms=sum(r[-2] for r in rows),
        log=sha(P/"server.stderr"),timing=sha(D/"timing-events.json.gz"),columns=["prompt","class","prefill_ms","prefill_tokens","decode_ms","decode_tokens","total_ms","total_tokens"]))
if __name__=="__main__":main()
