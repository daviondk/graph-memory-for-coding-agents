from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from run import *
import runpy

HERE=Path(__file__).resolve().parent
ARMS=("anchor/first","anchor/lex")
def predict():
    assert c.checksum(HERE/"PROTOCOL_RU.md")=="475e37cebff8745a2417a1c5dcbc7bb83bb2747d6e5c526aa23c1a617ff3f616"
    tok=c.tok()
    conn=sqlite3.connect((c.CACHE/"source-lookup.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    @lru_cache(maxsize=None)
    def end_options(d):
        body=conn.execute("SELECT body FROM source WHERE d=?",(d,)).fetchone()[0]
        offsets=tok.encode(body,add_special_tokens=False).offsets
        # Earlier starts include >256 invariant tokens after a whitespace boundary.
        cutoff=offsets[-257][0] if len(offsets)>257 else 0
        while cutoff>0 and not body[cutoff-1].isspace():cutoff-=1
        offsets={a for a,_ in offsets if a>=cutoff}
        if not cutoff:offsets.add(0)
        allowed=[]
        for a in sorted(offsets):
            rendered=f"[{d}:{a}] "+body[a:]
            n=len(tok.encode(rendered,add_special_tokens=False).ids)
            if n<=256:allowed.append((n,a))
        return allowed
    lock=c.read(D/"open-lock.json")
    assert c.checksum(D/"opens.json.gz")==lock["opens"]
    result=[]
    for row in c.read(D/"opens.json.gz"):
        vals={}
        for arm in ARMS:
            d,start,end,n,digest=row["arms"]["merged/"+arm]
            body=conn.execute("SELECT body FROM source WHERE d=?",(d,)).fetchone()[0]
            assert c.sha((f"[{d}:{start}] "+body[start:end]).encode())==digest
            eof=end==len(body);a=start
            if n<256 and eof:
                valid=[(m,z) for m,z in end_options(d) if z<=start]
                best=min([*valid,(n,start)],key=lambda p:(-p[0],p[1]))
                num,a=best
            else:num=n
            text=f"[{d}:{a}] "+body[a:end]
            assert len(tok.encode(text,add_special_tokens=False).ids)==num<=256 and a<=start<=end and num>=n
            vals[arm]=dict(span=[d,a,end],original=[d,start,end],tokens=num,previous=n,sha=c.sha(text.encode()),
                           at_eof=eof,changed=a<start,entire=(a==0 and eof))
        result.append({"q":row["q"],"arms":vals})
    conn.close()
    h=c.save(HERE/"forecasts.json.gz",result)
    print("sealed",c.save(HERE/"seal.json",dict(forecasts=h,original=c.checksum(D/"open-lock.json"),protocol=c.checksum(HERE/"PROTOCOL_RU.md"),code=c.checksum(Path(__file__)))))
def score():
    seal=c.read(HERE/"seal.json")
    assert c.checksum(HERE/"forecasts.json.gz")==seal["forecasts"]
    calc=runpy.run_path(str(T/"score.py"),run_name="transfer_score")
    gold,_=calc["labels"](c.get_views());opts=[];docs=[];out=[]
    for r in c.read(HERE/"forecasts.json.gz"):
        gs=calc["union"](gold[r["q"]][0]);den=sum(b-a for d,a,b in gs);docs.append(gs[0][0])
        by={}
        for arm in ARMS:
            rec=r["arms"][arm].copy()
            x=calc["overlap"](gs,[rec["span"]]);old=calc["overlap"](gs,[rec["original"]])
            assert x>=old
            rec.update(full=int(x==den),old_full=int(old==den),coverage=x/den)
            by[arm]=rec
        opts.append(by[ARMS[1]]["full"]-by[ARMS[0]]["full"])
        out.append({"q":r["q"],"arms":by})
    wp=opts.count(1);lp=opts.count(-1)
    stats={}
    for a in ARMS:
        vals=[r["arms"][a] for r in out]
        stats[a]={"success":sum(x["full"] for x in vals),"old_success":sum(x["old_full"] for x in vals),
           "mean_tokens":float(np.mean([x["tokens"] for x in vals])),"new_success":sum(x["full"]>x["old_full"] for x in vals),
           "eligible":sum(x["at_eof"] and x["previous"]<256 for x in vals),"moved":sum(x["changed"] for x in vals),
           "cap_unspent":sum(x["tokens"]<256 for x in vals),"entire_with_unspent":sum(x["entire"] and x["tokens"]<256 for x in vals)}
    out_hash=c.save(HERE/"outcomes.json.gz",out)
    summary=dict(n=len(out),metrics=stats,wins=wp,losses=lp,exact_p=float(binomtest(wp,wp+lp).pvalue) if wp+lp else 1,
         dialogue=inference(opts,[r["q"] for r in out]),doc=inference(opts,docs),
         any_changed=sum(any(r["arms"][a]["changed"] for a in ARMS) for r in out),
         paired_outcome_changed=sum((r["arms"][ARMS[1]]["old_full"]-r["arms"][ARMS[0]]["old_full"])!=x for r,x in zip(out,opts)),
         raw=out_hash,seal=c.checksum(HERE/"seal.json"))
    print(summary);print("sha",c.save(HERE/"results.json",summary))
if __name__=="__main__":
    globals()[sys.argv[1]]()
