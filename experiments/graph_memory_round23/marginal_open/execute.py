"""Execute at most one predetermined read per policy, without labels or policy changes."""
from concurrent.futures import ProcessPoolExecutor
from tokenizers import Tokenizer
import sqlite3
from common import *
from prepare import CACHE
def paid(tok,f,e,l):
    header=f"[{e}:{l}] ";text=header+f[l:]
    pos=min(len(text),4096)
    while True:
        while pos<len(text) and not text[pos].isspace():pos+=1
        ids=tok.encode(text[:pos],add_special_tokens=False)
        if len(ids.ids)>256 or pos==len(text):break
        pos=min(len(text),pos*2)
    cut=ids.offsets[256][0] if len(ids.ids)>256 else pos
    while True:
        n=len(tok.encode(text[:cut],add_special_tokens=False).ids)
        if n<=256:break
        cut-=1
    assert cut>=len(header)
    return [e,l,l+cut-len(header),n]
def shard(i):
    seal=read(D/"choice-seal.json");name,h,_=seal["parts"][i];assert sha(D/name)==h
    tok=Tokenizer.from_file(str(TOK));rows=read(D/name);groups={}
    for r in rows:groups.setdefault(r["t"],[]).append(r)
    reg=sqlite3.connect((PARENT/"registry.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    out=[];controls=read(D.parent/"address_open"/f"reads-{i}.json.gz")
    for t,records in sorted(groups.items()):
        src=read(CACHE/f"{i}-{t}.json.gz")["fields"];addr=dict(reg.execute("select e,eid from address where t=?",(t,)));cache={}
        for r in records:
            q=r["q"];action={}
            for a,pick in r["picks"].items():
                if pick is None:action[a]=None;continue
                e,l=pick[:2]
                if (e,l) not in cache:cache[e,l]=paid(tok,src[addr[e]],e,l)
                action[a]=cache[e,l]
            for a in ("bm25","first"):
                assert (action[a] or [-1,0,0,0])==controls[q]["read"]["ratio/merged/"+a]
            out.append({"q":q,"t":t,"open":action})
    reg.close();p=D/f"opened-{i}.json.gz";save(p,out);return [p.name,sha(p),len(out)]
def main():
    with ProcessPoolExecutor(2) as ex:rows=list(ex.map(shard,range(8)))
    assert sum(r[2] for r in rows)==2000
    save(D/"opened-seal.json",{"files":rows,"choice":sha(D/"choice-seal.json"),"code":sha(Path(__file__)),"same_as_old_controls":4000})
if __name__=="__main__":main()

