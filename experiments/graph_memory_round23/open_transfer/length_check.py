from run import *
import runpy
calc=runpy.run_path(str(T/"score.py"),run_name="transfer_gold")
def starts(tok,body,d,a,b):
    header=f"[{d}:{a}] "
    text=header+body[a:b]
    n0=len(tok.encode(text,add_special_tokens=False).ids)
    return text,header,n0
def attainable(tok,text,header,top):
    e=tok.encode(text,add_special_tokens=False)
    candidates={len(text)}
    low=max(0,top-12)
    for i in range(low,min(len(e.offsets),top+4)):
        candidates.update((e.offsets[i][0],e.offsets[i][1]))
    result={}
    for k in sorted(candidates):
        if k<=len(header):continue
        n=len(tok.encode(text[:k],add_special_tokens=False).ids)
        if n<=top:result[n]=k-len(header)
    return result
def main():
    seal=c.read(D/"open-lock.json"); assert c.checksum(D/"opens.json.gz")==seal["opens"]
    v=c.get_views();tok=c.tok();red=[]
    for row in c.read(D/"opens.json.gz"):
        first=row["arms"]["merged/anchor/first"];lex=row["arms"]["merged/anchor/lex"]
        raw=[]
        for d,a,b,n,digest in (first,lex):
            s,header,num=starts(tok,v["documents"][d][2],d,a,b)
            assert n==num and c.sha(s.encode())==digest
            raw.append((s,header))
        lim=min(first[3],lex[3])
        options=[attainable(tok,s,h,lim) for s,h in raw];same=set(options[0])&set(options[1])
        assert same
        common=max(same)
        spans=[[z[0],z[1],z[1]+n[common]] for z,n in zip((first,lex),options)]
        red.append({"q":row["q"],"spans":spans,"tokens":common,"min":lim})
    h=c.save(D/"length-matched-opens.json.gz",red)
    gold,_=calc["labels"](v)
    diffs=[];wins=[0,0];gs=[];bud=[]
    for row in c.read(D/"length-matched-opens.json.gz"):
        truth=calc["union"](gold[row["q"]][0])
        denom=sum(b-a for d,a,b in truth)
        val=[int(calc["overlap"](truth,[s])==denom) for s in row["spans"]]
        for i,y in enumerate(val):wins[i]+=y
        diffs.append(val[1]-val[0]);gs.append(truth[0][0]);bud.append(row["tokens"])
    wp=diffs.count(1);lp=diffs.count(-1)
    out=dict(scored=len(red),open_hash=h,exact_wp_equal=True,mean_tokens=float(np.mean(bud)),counts_first_lex=wins,
         gap_to_lesser_tokens_max=max(r["min"]-r["tokens"] for r in red),wins=wp,losses=lp,
         mcnemar=float(binomtest(wp,wp+lp).pvalue) if wp+lp else 1,dialogue=inference(diffs,[r["q"] for r in red]),doc=inference(diffs,gs))
    print(out);print(c.save(D/"length-sensitivity.json",out))
if __name__=="__main__":main()
