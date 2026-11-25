"""Select one database read from visible text, before loading evidence labels."""
from collections import Counter
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
import math
import os
from pathlib import Path
import re
import sqlite3
import sys

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"read_causes"))
from project import CACHE, TOK, Tokenizer, read, sha, write

SOURCE=D.parent/"read_causes"
WORDS=re.compile(r"[^\W_]+",re.UNICODE)

def terms(text):
    return Counter(WORDS.findall(text.casefold()))

def visible(scopes,body,tok):
    windows=[]
    for e,l,h in scopes:
        s=body[e][l:h]
        enc=tok.encode(s,add_special_tokens=False)
        if not enc.offsets:
            windows.append((e,l,terms(s)))
        for i in range(0,len(enc.offsets),128):
            left=0 if i==0 else enc.offsets[i][0]
            right=enc.offsets[i+128][0] if i+128<len(enc.offsets) else len(s)
            windows.append((e,l+left,terms(s[left:right])))
    return windows

def bm25(windows,question):
    q=set(terms(question))
    docs=[x[2] for x in windows]
    lengths=[sum(d.values()) for d in docs]
    avg=sum(lengths)/len(docs) or 1
    df=Counter(w for d in docs for w in d.keys()&q)
    weights={w:math.log1p((len(docs)-n+.5)/(n+.5)) for w,n in df.items()}
    def points(i):
        d=docs[i]
        norm=1.2*(.25+.75*lengths[i]/avg)
        return sum(weights[w]*d[w]*2.2/(d[w]+norm) for w in sorted(d.keys()&q))
    return max(range(len(windows)),key=points)

def paid_open(tok,source,e,l):
    s=source[l:]
    header=f"[{e}:{l}] "
    text=header+s
    # Grow to a word boundary, avoiding repeated full tokenization of large fields.
    end=min(len(text),4096)
    while True:
        while end<len(text) and not text[end].isspace(): end+=1
        enc=tok.encode(text[:end],add_special_tokens=False)
        if len(enc.ids)>256 or end==len(text): break
        end=min(len(text),end*2)
    cut=enc.offsets[256][0] if len(enc.ids)>256 else end
    while True:
        n=len(tok.encode(text[:cut],add_special_tokens=False).ids)
        if n<=256: break
        cut-=1
    assert cut>=len(header)
    return [e,l,l+cut-len(header),n]

def shard(idx):
    orig=read(SOURCE/"receipt-lock.json")
    receipts=SOURCE/f"receipts-{idx}.json.gz"
    assert sha(receipts)==orig["files"][receipts.name]
    source_rows=read(receipts)
    tok=Tokenizer.from_file(str(TOK))
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    grouped={}
    for row in source_rows: grouped.setdefault(row["t"],[]).append(row)
    out={}
    for t,rows in grouped.items():
        source=read(CACHE/f"{idx}-{t}.json.gz")
        questions=dict(source["q"])
        fields=source["fields"]
        address=dict(db.execute("SELECT e,eid FROM address WHERE t=?",(t,)))
        body={e:fields[eid] for e,eid in address.items()}
        @lru_cache(maxsize=256)
        def open_at(e,l):
            eid,ptr=db.execute("SELECT eid,ptr FROM address WHERE t=? AND e=?",(t,e)).fetchone()
            assert eid==address[e] and isinstance(ptr,str)
            return paid_open(tok,fields[eid],e,l)
        for row in rows:
            q=row["q"]; selections={}
            for a in ("ratio","skip"):
                for fmt in ("short","merged"):
                    key=f"{a}/{fmt}"
                    ranges=row["arms"][key]["paid"]["2048"][2]
                    windows=visible(ranges,body,tok)
                    if not windows:
                        for method in ("first","bm25"): selections[key+"/"+method]=[-1,0,0,0]
                        continue
                    pos=bm25(windows,questions[q])
                    for method,k in (("first",0),("bm25",pos)):
                        e,l,_=windows[k]
                        assert any(r[0]==e and r[1]<=l<r[2] for r in ranges)
                        selections[key+"/"+method]=open_at(e,l)
            assert q not in out
            out[q]={"t":t,"read":selections}
    db.close()
    path=D/f"reads-{idx}.json.gz";write(path,out)
    return path.name,sha(path)

def main():
    with ProcessPoolExecutor(2) as pool: files=dict(pool.map(shard,range(8)))
    write(D/"read-lock.json",{"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),
                             "source":sha(SOURCE/"receipt-lock.json"),"files":files})
if __name__=="__main__": main()
