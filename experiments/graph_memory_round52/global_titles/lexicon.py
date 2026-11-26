"""Tokenization for title BM25 and whole-title phrase matching; never reads evaluation labels."""
from collections import Counter
import argparse
import struct
from corpus import ROOT, WORK, read, save, hashfile
import re
import unicodedata

STOP=set("""a an the of and or was were is are be been being do does did has have had in on at by for with as from to into than that this it its his her their my your whom who whose when what which where how why both also then these those either same different respectively s""".split())
def tokens(text):
    return re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",text).lower())
def build_titles():
    words={"":0}
    with (WORK/"titles.txt").open(encoding="utf8") as f,(WORK/"lex.bin").open("wb") as out:
        for row in f:
            page,title=row.rstrip("\n").split("\t",1)
            ts=tokens(title)
            ids=[words.setdefault(t,len(words)) for t in ts]
            usable=int(any(t not in STOP for t in ts) and sum(map(len,ts))>=3)
            out.write(struct.pack(f"<IHH{len(ids)}I",int(page),len(ids),usable,*ids))
    with (WORK/"vocab.txt").open("w",encoding="utf8",newline="\n") as stream:
        for w in words:stream.write(w+"\n")
    (WORK/"stop.bin").write_bytes(bytes(int(w=="" or w in STOP) for w in words))
    questions=read(WORK/"questions.json.gz")
    with (WORK/"questions.in").open("w",encoding="ascii",newline="\n") as out:
        for q,text in sorted(questions.items()):
            out.write(q+" "+" ".join(str(words.get(t,0)) for t in tokens(text))+"\n")
    save(ROOT/"lexicon.json",dict(terms=len(words),source=hashfile(ROOT/"source.json"),
         stopwords=sorted(STOP),files={k:hashfile(WORK/k) for k in ("lex.bin","vocab.txt","stop.bin","questions.in")}))
def vocab():
    with (WORK/"vocab.txt").open(encoding="utf8") as f:
        return {line.rstrip("\n"):i for i,line in enumerate(f)}
if __name__=="__main__":
    build_titles()

