"""Reconstruct ranges using only the payload already delivered to the receiver."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"address_open"))
from choose import CACHE,TOK,SOURCE,Tokenizer,read,sha,write,visible,bm25,paid_open

def assemble(pieces):
    fields=defaultdict(list)
    for idx,(e,l,text) in enumerate(pieces):
        assert text
        fields[e].append((l,idx,text))
    groups=[]
    for e,payload in fields.items():
        active=None
        for l,rank,text in sorted(payload):
            if active and l<=active[1]+len(active[2]):
                overlap=active[1]+len(active[2])-l
                n=min(len(text),overlap);at=l-active[1]
                assert active[2][at:at+n]==text[:n]
                active[2]+=text[n:]
                active[3]=min(active[3],rank)
            else:
                if active: groups.append(active)
                active=[e,l,text,rank]
        if active: groups.append(active)
    return [g[:3] for g in sorted(groups,key=lambda g:g[3])]

def render(pieces,tok,cap):
    pos=0;parts=[];starts=[]
    for i,(e,l,text) in enumerate(pieces):
        header=("\n" if i else "")+f"[{e}:{l}] "
        parts.extend((header,text));pos+=len(header);starts.append(pos);pos+=len(text)
    full="".join(parts)
    enc=tok.encode(full,add_special_tokens=False);raw=len(enc.ids)
    cut=enc.offsets[cap][0] if raw>cap else len(full)
    while True:
        paid=len(tok.encode(full[:cut],add_special_tokens=False).ids)
        if paid<=cap: break
        cut-=1
    clipped=[(e,l,text[:cut-p]) for p,(e,l,text) in zip(starts,pieces) if cut>p]
    return raw,paid,clipped

def canonical(ranges):
    groups=defaultdict(list)
    for e,l,h in ranges: groups[e].append((l,h))
    out=[]
    for e,entries in sorted(groups.items()):
        for l,h in sorted(entries):
            if out and out[-1][0]==e and out[-1][2]>=l:out[-1][2]=max(h,out[-1][2])
            else:out.append([e,l,h])
    return out

def shard(i):
    receipts=SOURCE/f"receipts-{i}.json.gz"
    assert sha(receipts)==read(SOURCE/"receipt-lock.json")["files"][receipts.name]
    traces=defaultdict(list)
    for r in read(receipts): traces[r["t"]].append(r)
    tok=Tokenizer.from_file(str(TOK))
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    out={}
    for t,rows in traces.items():
        data=read(CACHE/f"{i}-{t}.json.gz");questions=dict(data["q"])
        fields={e:data["fields"][eid] for e,eid in db.execute("SELECT e,eid FROM address WHERE t=?",(t,))}
        for r in rows:
            q=r["q"];orig=r["arms"]["ratio/short"]["paid"]["2048"]
            sent=[(e,l,fields[e][l:h]) for e,l,h in orig[2]]
            assembled=assemble(sent)
            assert canonical(orig[2])==canonical([(e,l,l+len(x)) for e,l,x in assembled])
            raw,paid,shown=render(assembled,tok,2048)
            intervals=[];windows=[]
            for e,l,text in shown:
                intervals.append([e,l,l+len(text)])
                for _,begin,counts in visible([[0,0,len(text)]],{0:text},tok):
                    windows.append((e,l+begin,counts))
            if windows:
                k=bm25(windows,questions[q]);e,l,_=windows[k]
                (eid,)=db.execute("SELECT eid FROM address WHERE t=? AND e=?",(t,e)).fetchone()
                opened=paid_open(tok,data["fields"][eid],e,l)
            else:opened=[-1,0,0,0]
            out[q]={"t":t,"tokens_in":orig[0],"raw":raw,"tokens_internal":paid,"shown":intervals,"opened":opened}
    db.close()
    path=D/f"receiver-{i}.json.gz";write(path,out);return path.name,sha(path)

def main():
    with ProcessPoolExecutor(2) as pool: files=dict(pool.map(shard,range(8)))
    write(D/"receiver-lock.json",{"files":files,"protocol":sha(D/"PROTOCOL_RU.md"),"source":sha(SOURCE/"receipt-lock.json"),"code":sha(Path(__file__))})
if __name__=="__main__":main()
