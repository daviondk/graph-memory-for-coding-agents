"""Factor one database read into choosing a source field and an offset."""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import math
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent
PARENT=D.parent/"address_open"; sys.path.insert(0,str(PARENT))
from choose import CACHE,TOK,SOURCE,Tokenizer,read,sha,write,terms,visible,paid_open

def rank(windows,question):
    query=set(terms(question))
    lengths=[sum(d.values()) for _,_,d in windows]
    avg=sum(lengths)/len(lengths) or 1
    df=Counter(w for _,_,d in windows for w in query&d.keys())
    weights={w:math.log1p((len(lengths)-n+.5)/(n+.5)) for w,n in df.items()}
    scores=[]
    for (_,_,d),size in zip(windows,lengths):
        norm=1.2*(.25+.75*size/avg)
        scores.append(sum(weights[w]*d[w]*2.2/(d[w]+norm) for w in sorted(query&d.keys())))
    order=sorted(range(len(windows)),key=lambda i:-scores[i])
    return order

def shard(i):
    path=SOURCE/f"receipts-{i}.json.gz"
    assert sha(path)==read(SOURCE/"receipt-lock.json")["files"][path.name]
    original=PARENT/f"reads-{i}.json.gz"
    assert sha(original)==read(PARENT/"read-lock.json")["files"][original.name]
    controls=read(original)
    by_trace=defaultdict(list)
    for row in read(path): by_trace[row["t"]].append(row)
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    tok=Tokenizer.from_file(str(TOK));out={}
    for t,rows in by_trace.items():
        data=read(CACHE/f"{i}-{t}.json.gz"); questions=dict(data["q"])
        body={e:data["fields"][eid] for e,eid in db.execute("SELECT e,eid FROM address WHERE t=?",(t,))}
        @lru_cache(maxsize=256)
        def action(e,l):
            hit=db.execute("SELECT eid,ptr FROM address WHERE t=? AND e=?",(t,e)).fetchone()
            assert hit and data["fields"][hit[0]]==body[e]
            return paid_open(tok,body[e],e,l)
        for row in rows:
            q=row["q"];result={}
            for way in ("ratio/merged","ratio/short","skip/merged","skip/short"):
                windows=visible(row["arms"][way]["paid"]["2048"][2],body,tok)
                if windows:
                    order=rank(windows,questions[q]);lex=order[0]
                    for field,k in (("anchor",0),("lex",lex)):
                        e=windows[k][0]
                        first=next(j for j,v in enumerate(windows) if v[0]==e)
                        best=next(j for j in order if windows[j][0]==e)
                        for offset,pos in (("first",first),("lex",best)):
                            result[f"{way}/{field}/{offset}"]=action(e,windows[pos][1])
                else:
                    for f in ("anchor","lex"):
                        for o in ("first","lex"):result[f"{way}/{f}/{o}"]=[-1,0,0,0]
                for name,old in (("anchor/first","first"),("lex/lex","bm25")):
                    assert result[f"{way}/{name}"]==controls[q]["read"][f"{way}/{old}"]
            assert q not in out
            out[q]={"t":t,"read":result}
    db.close()
    dest=D/f"reads-{i}.json.gz";write(dest,out);return dest.name,sha(dest)

def main():
    with ProcessPoolExecutor(2) as pool: dist=dict(pool.map(shard,range(8)))
    write(D/"read-lock.json",{"files":dist,"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),
      "controls":sha(PARENT/"read-lock.json"),"source":sha(SOURCE/"receipt-lock.json")})
if __name__=="__main__":main()
