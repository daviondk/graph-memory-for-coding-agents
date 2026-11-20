"""Choose among already observed declarations using a draft as an additional read key."""
import re, math, sys, gzip, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
import pyarrow.parquet as pq
from infer import read, save, sha, D
from evidence import R4, trim, query, local_view, record, wt
from prepare5 import BAD
from data_io import rows, panel_name

P=R4/"repo"
call=re.compile(r"\b([A-Za-z_$][\w$]*)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(")
binding=re.compile(r"\b([A-Z][\w$]*)(?:\s*<[^;\n()]{1,80}>)?(?:\s*\[\s*\])?\s+([a-zA-Z_$][\w$]*)\b")
common=set("equals hashcode tostring size get set add remove contains isempty toarray compareto println print valueof of getclass iterator next hasnext build append put clear close read write run clone entryset tolist stream map collect".split())

def addresses(texts, rank, ctx, draft):
    records=[record(s) for s in texts];n=len(records)
    avg=sum(r["tokens"] for r in records)/n
    tokens=wt("\n".join(ctx.splitlines()[-3:])+"\n"+draft)
    df=Counter(t for r in records for t in tokens & r["words"])
    def bm(i):
        r=records[i];adj=1.2*(.25+.75*r["tokens"]/max(1,avg))
        return sum(math.log1p((n-df[t]+.5)/(df[t]+.5))*2.2*r["counter"][t]/(r["counter"][t]+adj) for t in sorted(tokens & r["words"]))
    lex=max(rank,key=bm)
    binds={v:t.lower() for t,v in binding.findall(ctx)}
    calls=call.findall(draft)
    newtypes={t.lower() for t in re.findall(r"\bnew\s+([A-Z][\w$]*)\s*(?:<[^>]*>)?\s*\(",draft)}
    method_count=Counter(m for r in records for m in r["members"])
    roots=Counter(r["root"] for r in records)
    def strength(i):
        r=records[i]
        typed=sum(r["root"] in {binds.get(v),v.lower() if v[0].isupper() else None} and m.lower() in r["members"] for v,m in calls)
        cons=int(r["root"] in newtypes and roots[r["root"]]==1)
        uniq=sum(m.lower() not in common and m.lower() in r["members"] and method_count[m.lower()]==1 for _,m in calls)
        return typed,cons,uniq
    ver=max(rank,key=strength);a,b,c=strength(ver)
    reason="receiver_type" if a else "constructor" if b else "unique_member" if c else "no_link"
    return lex,ver,reason

def prepare():
    ranks={(k,i):(repo,order["graph"]) for k,i,repo,h,order in map(json.loads,gzip.open(P/"archive.pred.jsonl.gz","rt",encoding="utf8"))}
    used={x["repo"] for k in "AB" for x in read(k+"_packets.json.gz")}
    original=set(used); queues={}; pool={}
    for path in sorted((P/"archive_inputs").glob("*.parquet")):
        p=panel_name(path.stem); buckets=defaultdict(list)
        for i,name in enumerate(pq.read_table(path,columns=["repo_name"]).column(0).to_pylist()):
            if name not in original:buckets[name].append(i)
        key=lambda i:sha("r5-adaptive-new|"+p+"|"+str(i))
        ids={i for group in buckets.values() for i in sorted(group,key=key)[:3]}
        queues[p]=sorted(ids,key=key)
        for i,r in enumerate(rows(path,["repo_name","file_path","code","context"])):
            if i not in ids:continue
            ctx,ct=trim("\n".join(r["code"].splitlines()[-30:]),1024,True);texts=r["context"]
            if BAD.search("\n".join([r["repo_name"],r["file_path"],ctx,*texts])):continue
            repo,rank=ranks[p,i];assert repo==r["repo_name"]
            pool[p,i]=dict(id=p+"|"+str(i),repo=repo,panel=p,file=path.name,local_index=i,ctx=ctx,ctx_tokens=ct,rank=rank,texts=texts)
    out=[];j=Counter();counts=Counter()
    while True:
        before=len(out)
        for p,indices in queues.items():
            while counts[p]<24 and j[p]<len(indices):
                i=indices[j[p]];j[p]+=1;x=pool.get((p,i))
                if x is None or x["repo"] in used:continue
                out.append(x);used.add(x["repo"]);counts[p]+=1;break
        if len(out)==before:break
    save("C_visible_source.json.gz",out)
    save("C0_packets.json.gz",[{k:v for k,v in x.items() if k!="texts"}|{"snippets":{"empty":("(no external fragment)",0)}} for x in out])
    lock("C0",counts,["C_visible_source.json.gz","A_packets.json.gz","B_packets.json.gz"])
    print("C0",len(out),counts,flush=True)

def lock(k,counts,extras):
    files=["C_PROTOCOL_RU.md","adaptive.py","evidence.py","infer.py",k+"_packets.json.gz"]+extras
    save(k+"_data_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"strata":counts,"sha":{f:sha((D/f).read_bytes()) for f in files}})

def finish():
    manifest=read("C0_decisions.json"); ids=read("C0_assignment.json");out=[];counts=Counter()
    for x in read("C_visible_source.json.gz"):
        key=ids[x["id"]]["empty"];p="C0_calls/"+key+".json.gz";assert manifest[key+".json.gz"]==sha((D/p).read_bytes())
        msg=read(p)["reply"]["choices"][0]["message"]["content"] or ""
        draft=next((s.strip() for s in msg.splitlines() if s.strip() and not s.strip().startswith(chr(96)*3)),"")
        filtered=bool(BAD.search(draft));d="" if filtered else draft
        texts=x.pop("texts");ctx=x["ctx"];rank=x["rank"];top=rank[0]
        lex,verified,reason=addresses(texts,rank,ctx,d)
        q=query(ctx+"\n"+d); addrs={"head":top,"static_focus":top,"draft_lex":lex,"verified":verified}
        snippets={a:(trim(texts[i],256) if a=="head" else local_view(q,texts[i],256)) for a,i in addrs.items()}
        out.append(x|dict(snippets=snippets,addresses=addrs,draft_sha=key,reason=reason,draft_filtered=filtered))
        counts[x["panel"]]+=1
    save("C_packets.json.gz",out);lock("C",counts,["C0_decisions.json","C0_assignment.json","C_visible_source.json.gz"])
    print("C",len(out),Counter(row["reason"] for row in out),flush=True)
if __name__=="__main__":(prepare if sys.argv[1]=="prepare" else finish)()

