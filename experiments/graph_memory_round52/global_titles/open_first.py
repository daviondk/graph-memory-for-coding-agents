"""Open first documents by row, expose a token-limited prefix, and resolve only visible targets."""
from collections import defaultdict,Counter
from pathlib import Path
from urllib.parse import unquote
from tokenizers import Tokenizer
from corpus import ROOT, WORK, ZIP, SOURCE, title_rows, hashfile, read, save
from lexicon import tokens,vocab
import json
import unicodedata

TOKENIZER=Path("D:/CodexResearch/x20-r23-multidoc2dial/model/tokenizer.json")

def canonical(title):
    return unicodedata.normalize("NFC"," ".join(title.replace("_"," ").split()))

def destination(url):
    if not isinstance(url,str) or "://" in url or url.startswith("/"):return ""
    try:return canonical(unquote(url.split("#",1)[0],errors="strict"))
    except UnicodeError:return ""

def extract():
    tokenizer=Tokenizer.from_file(str(TOKENIZER));questions={};pages=set()
    for line in (WORK/"seed.tsv").read_text().splitlines():
        q,idx,wiki,plain,n=line.split("\t");questions[q]=int(idx);pages.add(int(idx))
    payload={};target_ids=set();target_titles=set();malformed=0
    for idx,(page,name,line) in enumerate(title_rows()):
        if idx not in pages:continue
        obj=json.loads(line);ss=obj["sentences"];body=" ".join(ss)
        offsets=tokenizer.encode(body,add_special_tokens=False).offsets[:192]
        end=offsets[-1][1] if offsets else 0
        starts=[];a=0
        for sentence in ss:starts.append(a);a+=len(sentence)+1
        visible=[]
        for m in obj["mentions"]:
            j,start,stop=(m.get(k) for k in ("sent_idx","start","end"))
            if not isinstance(j,int) or j<0 or j>=len(ss):malformed+=1;continue
            if starts[j]>=end:continue
            if not isinstance(start,int):malformed+=1;continue
            if starts[j]+start>=end:continue
            if not isinstance(stop,int) or not 0<=start<stop<=len(ss[j]):malformed+=1;continue
            if starts[j]+stop>end:continue
            tgt=destination(m.get("ref_url"));refs=sorted({int(v) for v in m.get("ref_ids",[]) or [] if str(v).isdecimal()})
            anchor=ss[j][start:stop]
            if not anchor.strip(): continue
            target_ids.update(refs)
            if tgt:target_titles.add(tgt)
            visible.append([starts[j]+start,starts[j]+stop,anchor,tgt,refs])
        payload[idx]=[page,name,body[:end],visible]
    assert set(payload)==pages
    by_id=defaultdict(list);by_title=defaultdict(list)
    with (WORK/"titles.txt").open(encoding="utf8") as f:
        for idx,line in enumerate(f):
            i,title=line.rstrip("\n").split("\t",1);i=int(i);t=canonical(title)
            if i in target_ids:by_id[i].append(idx)
            if t in target_titles:by_title[t].append(idx)
    dictionary=vocab(); projections={};addr=Counter()
    for idx,(page,title,text,mentions) in payload.items():
        links=defaultdict(list)
        for start,end,anchor,dest,refs in mentions:
            direct=set(by_title.get(dest,[]));indirect={row for v in refs for row in by_id.get(v,[])}
            if len(direct)==1:
                choices=direct if not indirect or direct&indirect else set()
            elif direct and indirect:choices=direct&indirect
            else:choices=indirect
            if len(choices)!=1:addr["unresolved"]+=1;continue
            target=next(iter(choices))
            if target==idx:continue
            links[target].append([start,end,anchor,dest,refs]);addr["resolved"]+=1
        projections[idx]=dict(wiki=page,title=title,prefix=text,links=links)
    save(WORK/"opened.json.gz",projections)
    with (WORK/"second.in").open("w",encoding="ascii",newline="\n") as f:
        for q,i in sorted(questions.items()):
            r=projections[i];links=sorted(r["links"]);ids=[dictionary.get(t,0) for t in tokens(r["prefix"])]
            f.write(" ".join(map(str,[q,i,len(links),*links,*ids]))+"\n")
    save(ROOT/"opening.json",dict(first_sources=len(pages),anchors=addr,malformed=malformed,
         tokenizer=hashfile(TOKENIZER),seed=hashfile(WORK/"seed.tsv"),second_inputs=hashfile(WORK/"second.in"),
         opened=hashfile(WORK/"opened.json.gz"),kernel=hashfile(ROOT/"retrieval.cpp")))
if __name__=="__main__":extract()

