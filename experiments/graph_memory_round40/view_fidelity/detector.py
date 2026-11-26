"""Pure display-only address gate, frozen without reading held-out edit receipts."""
from data import D,SPAN,sha,h,split,raw_events,fixed,save,read
from examine import display,feature_rows,ROW,R38_OMIT,OMIT


def gate(ob):
    rows,headers,clip=display(ob)
    ids=sorted(rows)
    breaks=[a+1 for a,b in zip(ids,ids[1:]) if b>a+1]
    body="\n".join(p["text"] for p in ob["content"] if isinstance(p,dict) and isinstance(p.get("text"),str))
    active=False;markers=[]
    for text in body.splitlines():
        if "cat -n" in text and text.rstrip().endswith("on "+ob["path"]+":"):
            active=True
            continue
        m=ROW.fullmatch(text)
        if active and m:
            if R38_OMIT.search(m[2]) or OMIT.search(m[2]):
                markers.append(int(m[1]))
        elif active:
            active=False
    flagged=bool(clip or breaks or headers!=1)
    cut=min(markers+breaks) if markers or breaks else (0 if flagged else float("inf"))
    if headers!=1:
        cut=0
    return {n:[1,int(not flagged),int(n<cut)] for n in ids},dict(headers=headers,markers=markers,breaks=breaks,
        cut=None if cut==float("inf") else cut)


def main():
    rows,test=split()
    plans,visible,schedule=fixed()
    raw=raw_events(rows,receipts=False)
    public=feature_rows(rows,raw,plans,visible,schedule)
    out=[];slices=[]
    for r in rows:
        labels,info=gate(raw[r["rid"]][r["view"]]["observation"])
        for f in public[r["rid"],r["event"]][1]:
            out.append([r["rid"],r["event"],f["n"],h(r["issue"]),int(r["issue"] in test),f["full_reuse_selected"],f["line_probe_hash"],labels[f["n"]]])
        slices.append([r["rid"],r["event"],info])
    save(D/"predictions.json.gz",out)
    save(D/"display-boundaries.json.gz",slices)
    save(D/"prediction-seal.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),addendum=sha(D/"DETECTOR_RU.md"),
        code=sha(D/"detector.py"),parser=sha(D/"examine.py"),scored_input=sha(SPAN/"scored.json.gz"),
        discovery=sha(D/"discovery-verified.json.gz"),rows=len(out),predictions=sha(D/"predictions.json.gz"),
        boundaries=sha(D/"display-boundaries.json.gz"),test_issues=sorted(h(i) for i in test)))
    print("Frozen",len(out),sha(D/"predictions.json.gz"))


if __name__=="__main__":
    main()
