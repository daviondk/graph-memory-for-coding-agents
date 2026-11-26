"""Build query-local, lossless SQL projections for fixed examples from the full directory."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import math
import sqlite3
import sys

HERE=Path(__file__).resolve().parent
G=HERE.parent/"global_titles";P=HERE.parent/"global_policy"
sys.path.insert(0,str(G))
from corpus import read,save,WORK,hashfile
from verify_scan import enumerate_titles
from lexicon import tokens,STOP

def choose(rows,grades,arms):
    groups=defaultdict(list)
    for q,r in rows.items():
        direct=r["gates"][1][1]>0
        results=grades[q][1]
        graph,literal,uncond=[results[arms.index(k)] for k in ("primary_href","primary_text","href_first")]
        label=("direct-gain" if direct and graph>uncond else "direct-loss" if direct and graph<uncond else
               "link-gain" if not direct and graph>literal else "link-loss" if not direct and graph<literal else "")
        if label:groups[label].append(q)
    assert len(groups)==4
    return {q:group for group,qs in sorted(groups.items()) for q in sorted(qs,key=lambda k:sha256(("demo52|"+k).encode()).digest())[:2]}

def windows(seq):
    return {tuple(seq[i:j]):(i,j) for i in range(len(seq)) for j in range(i+1,len(seq)+1)}

def build():
    rows=read(P/"predictions.json.gz");grades=read(P/"graded-rows.json.gz");arms=read(P/"routes.json")["arms"]
    chosen=choose(rows,grades,arms);queries=read(WORK/"questions.json.gz");opened=read(WORK/"opened.json.gz")
    labels=read(G/"support.json.gz");catalog={}
    with (WORK/"vocab.txt").open(encoding="utf8") as f:
        for i,line in enumerate(f):catalog[line.rstrip("\n")]=i
    stop=(WORK/"stop.bin").read_bytes();dfs=Counter();total=0;n=0;keep={}
    inputs={};needed=defaultdict(set);fixed=defaultdict(set);want=set()
    for q in chosen:
        r=rows[q];opening=opened[str(r["seed"])]
        qt=tokens(queries[q]);pt=tokens(opening["prefix"]);target=tokens(opening["title"]);m=len(target)
        occ={j for i in range(len(qt)) if m and qt[i:i+m]==target for j in range(i,i+m)}
        def toids(xs):return tuple(catalog.get(x,0) for x in xs)
        xx,yy=toids(qt),toids(pt)
        want.update(w for w in (*xx,*yy) if not stop[w])
        li={int(i):v for i,v in opening["links"].items()}
        base=r["choices"][arms.index("free")]
        for addr in [base,*li]:fixed[addr].add(q)
        for seq in set(windows(xx))|set(windows(yy)):needed[seq].add(q)
        inputs[q]=(xx,yy,occ,set(toids(target)),li,base)
    for idx,pg,seq,usable in enumerate_titles():
        content=tuple(w for w in seq if not stop[w]);total+=len(content);n+=1
        dfs.update(want.intersection(content))
        qq=set(fixed.get(idx,()))
        if usable:qq.update(needed.get(seq,()))
        for q in qq:
            if idx!=rows[q]["seed"]:keep.setdefault(q,{})[idx]=(pg,seq,content,usable)
    avg=total/n;df_idf={w:math.log1p((n-df+.5)/(df+.5)) for w,df in dfs.items()}
    names_wanted={i for d in keep.values() for i in d};names={}
    with (WORK/"titles.txt").open(encoding="utf8") as f:
        for idx,line in enumerate(f):
            if idx in names_wanted:names[idx]=line.rstrip("\n").split("\t",1)[1]
    dbfile=HERE/"directory.sqlite"
    con=sqlite3.connect(dbfile)
    with con:
        con.execute("DROP TABLE IF EXISTS episodes");con.execute("DROP TABLE IF EXISTS candidates")
        con.execute("CREATE TABLE episodes(q TEXT PRIMARY KEY,scenario TEXT,question TEXT,seed TEXT,prefix TEXT)")
        con.execute("""CREATE TABLE candidates(q TEXT,id INTEGER,title TEXT,page INTEGER,score REAL,
            literal INTEGER,href INTEGER,base INTEGER,direct_words INTEGER,df INTEGER,anchor TEXT,
            PRIMARY KEY(q,id)) WITHOUT ROWID""")
        audit={}
        for q,scenario in chosen.items():
            xx,yy,occupied,seedwords,links,base=inputs[q];xset,yset=set(xx),set(yy)
            opening=opened[str(rows[q]["seed"])]
            con.execute("INSERT INTO episodes VALUES(?,?,?,?,?)",(q,scenario,queries[q],opening["title"],opening["prefix"]))
            for idx,(pg,seq,content,usable) in keep[q].items():
                cnt=Counter(content);norm=1.2*(.25+.75*len(content)/avg)
                value=sum((df_idf[w]*((w in xset)+.25*(w in yset)))*(2.2*cnt[w]/(cnt[w]+norm)) for w in sorted(set(cnt)&(xset|yset)))
                literal=usable and seq in windows_cache(yy)
                direct=0
                if usable and occupied and set(cnt)-seedwords:
                    for i in range(len(xx)-len(seq)+1):
                        if xx[i:i+len(seq)]==seq and occupied.isdisjoint(range(i,i+len(seq))):direct=len(cnt);break
                df=dfs.get(next(iter(cnt)),0) if direct==1 else 0
                anchor=links[idx][0][2] if idx in links else ""
                con.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (q,idx,names[idx],pg,value,int(literal),int(idx in links),int(idx==base),direct,df,anchor))
            audit[q]=dict(support=labels[q][1],expected={k:rows[q]["choices"][arms.index(k)] for k in arms})
        save(HERE/"audit.json",audit)
    con.execute("VACUUM");con.close()
    save(HERE/"build.json",dict(cases=len(chosen),candidates=sum(map(len,keep.values())),source_directory=n,
         receipt=hashfile(P/"prediction-seal.json"),files={k:hashfile(HERE/k) for k in ["directory.sqlite","audit.json"]}))
from functools import lru_cache
@lru_cache(maxsize=16)
def windows_cache(seq):return set(windows(seq))
if __name__=="__main__":build()

