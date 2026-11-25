"""One bounded read, optionally extending an underfilled end-of-field suffix to the left."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
import sqlite3
import sys
D=Path(__file__).resolve().parent
UP=D.parent/"field_first";sys.path.insert(0,str(UP))
from decide import CACHE,TOK,SOURCE,Tokenizer,read,sha,write

def shard(i):
    source=UP/f"reads-{i}.json.gz"
    assert sha(source)==read(UP/"read-lock.json")["files"][source.name]
    groups=defaultdict(list);out={}
    for q,row in read(source).items():groups[row["t"]].append((q,row["read"]))
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    tok=Tokenizer.from_file(str(TOK))
    for t,rows in groups.items():
        fields=read(CACHE/f"{i}-{t}.json.gz")["fields"]
        @lru_cache(maxsize=24)
        def positions(eid):
            s=fields[eid];tokens=tok.encode(s,add_special_tokens=False)
            # Filter offsets beyond the last 264 original WordPieces before exact re-tokenization.
            out={l for l,_ in tokens.offsets[-264:]}
            if len(tokens.ids)<=264:out.add(0)
            return sorted(out)
        for q,arms in rows:
            outcomes={}
            for name in ("first","lex"):
                e,l,h,n=old=arms[f"ratio/merged/anchor/{name}"]
                (eid,)=db.execute("SELECT eid FROM address WHERE t=? AND e=?",(t,e)).fetchone()
                s=fields[eid]
                assert h<=len(s) and n<=256 and len(tok.encode(f"[{e}:{l}] "+s[l:h],add_special_tokens=False).ids)==n
                new=old;offered=bool(h==len(s) and n<256 and l>0)
                if offered:
                    for start in positions(eid):
                        if start>=l:break
                        cost=len(tok.encode(f"[{e}:{start}] "+s[start:],add_special_tokens=False).ids)
                        if cost<=256:
                            new=[e,start,h,cost];break
                assert new[1]<=l and new[2]==h and new[3]<=256
                outcomes[name]=[old,new,offered]
            out[q]={"t":t,"arms":outcomes}
    db.close()
    dest=D/f"extended-{i}.json.gz";write(dest,out);return dest.name,sha(dest)
def main():
    with ProcessPoolExecutor(2) as pool: files=dict(pool.map(shard,range(8)))
    write(D/"extend-lock.json",{"source":sha(UP/"read-lock.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"files":files})
if __name__=="__main__":main()
