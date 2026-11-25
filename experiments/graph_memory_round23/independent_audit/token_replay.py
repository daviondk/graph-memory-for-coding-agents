"""Rebuild real visible text and source-open decisions on a hash-stratified subset."""
from collections import Counter,defaultdict
import hashlib,math,re,sys
from tokenizers import Tokenizer
from audit import D,R22,CAUSE,OPEN,FIELD,RECEIVE,CACHE,TOK,load,save,sha
WORDS=re.compile(r"[^\W_]+",re.UNICODE)

def clipped(tok,text,cap):
    enc=tok.encode(text,add_special_tokens=False)
    end=len(text) if len(enc.ids)<=cap else enc.offsets[cap][0]
    while len(tok.encode(text[:end],add_special_tokens=False).ids)>cap:end-=1
    return text[:end],len(tok.encode(text[:end],add_special_tokens=False).ids)

def components(parts,sources,join_ws):
    by=defaultdict(list)
    for j,(e,a,b) in enumerate(parts):by[e].append((a,b,j))
    out=[];gap=0
    for e,ls in by.items():
        current=[]
        for a,b,j in sorted(ls):
            if current:
                g=a-current[1]
                if g<=0 or (join_ws and g<=8 and sources[e][current[1]:a].isspace()):
                    current[1]=max(b,current[1]);current[2]=min(current[2],j);gap+=max(0,g);continue
                out.append((current[2],e,current[0],current[1]))
            current=[a,b,j]
        if current:out.append((current[2],e,current[0],current[1]))
    return [(e,a,b) for j,e,a,b in sorted(out)],gap

def payload(tok,fragments,fmt,cap,ad):
    chunks=[];coords=[];offset=0
    for i,(e,l,body) in enumerate(fragments):
        tag=("" if i==0 else "\n")
        if fmt=="full":
            import json
            tag+=json.dumps([*ad[e],l],separators=(",",":"),ensure_ascii=False)+" "
        elif fmt!="bare":tag+=f"[{e}:{l}] "
        chunks.extend((tag,body));offset+=len(tag)
        coords.append((offset,e,l,body));offset+=len(body)
    text="".join(chunks);shown,paid=clipped(tok,text,cap)
    visible=[(e,l,body[:len(shown)-start]) for start,e,l,body in coords if start<len(shown)]
    return shown,paid,visible

def reconstruct(fragments):
    # Use an address→character map built strictly from the delivered payload.
    material=defaultdict(dict);ranks=defaultdict(dict)
    for i,(e,l,s) in enumerate(fragments):
        for j,ch in enumerate(s,l):
            assert j not in material[e] or material[e][j]==ch
            material[e][j]=ch;ranks[e][j]=min(i,ranks[e].get(j,i))
    runs=[]
    for e,code in material.items():
        start=None;seq=[];k=None;last=-2
        for pos,ch in sorted(code.items()):
            if pos!=last+1 and start is not None:
                runs.append((k,e,start,"".join(seq)));start=None
            if start is None:start=pos;seq=[];k=ranks[e][pos]
            seq.append(ch);k=min(k,ranks[e][pos]);last=pos
        if start is not None:runs.append((k,e,start,"".join(seq)))
    return [(e,l,s) for _,e,l,s in sorted(runs)]

def windows(tok,frags):
    out=[]
    for e,l,src in frags:
        offsets=tok.encode(src,add_special_tokens=False).offsets
        cuts=[0]+[offsets[k][0] for k in range(128,len(offsets),128)]+[len(src)]
        for a,b in zip(cuts,cuts[1:]):
            out.append((e,l+a,Counter(WORDS.findall(src[a:b].casefold()))))
    return out
def order(wins,query):
    vocab=sorted(set(WORDS.findall(query.casefold())));n=len(wins)
    docs=[z[2] for z in wins];length=[sum(doc.values()) for doc in docs];avg=sum(length)/max(n,1) or 1
    idf={w:math.log1p((n-(df:=sum(w in doc for doc in docs))+.5)/(df+.5)) for w in vocab}
    def score(i):
        doc=docs[i];norm=1.2*(.25+.75*length[i]/avg)
        return sum(idf[w]*doc[w]*2.2/(doc[w]+norm) for w in vocab if w in doc)
    return sorted(range(n),key=lambda j:(-score(j),j))
def next_read(tok,body,e,l,store):
    if (e,l) not in store:
        head=f"[{e}:{l}] ";full=head+body[e][l:];text,n=clipped(tok,full,256)
        assert text.startswith(head)
        store[e,l]=[e,l,l+len(text)-len(head),n]
    return store[e,l]
def main():
    sel=load(D/"sample.json");wanted={q for arr in sel.values() for q in arr}
    tok=Tokenizer.from_file(str(TOK));assert tok.truncation is None
    counts=Counter();scope=Counter();distinct_bytes=0
    for i in range(8):
        receipts=load(CAUSE/f"receipts-{i}.json.gz");opens=load(OPEN/f"reads-{i}.json.gz")
        factors=load(FIELD/f"reads-{i}.json.gz");recv=load(RECEIVE/f"receiver-{i}.json.gz")
        original={r["t"]:r for r in load(R22/f"no-next-decisions-{i}.json.gz")}
        for r in receipts:
            q,t=r["q"],r["t"]
            if q not in wanted:continue
            counts["questions"]+=1;orig=original[t];ad=orig["addresses"]
            source=load(CACHE/f"{i}-{t}.json.gz");body={e:source["fields"][p[0]] for e,p in enumerate(ad)}
            question=dict(source["q"])[q];stored={};short=None
            for a in ("skip","ratio"):
                raw=[tuple(orig["used"][k][:3]) for k in orig["picks"][q][a]]
                for kind in ("bare","short","full","merged","space"):
                    spans,gap=components(raw,body,kind=="space") if kind in ("merged","space") else (raw,0)
                    record=r["arms"][a+"/"+kind];assert record["count"]==len(spans) and record["added_ws"]==gap
                    f=[(e,l,body[e][l:h]) for e,l,h in spans]
                    for cap in (512,1024,2048):
                        text,n,pieces=payload(tok,f,kind,cap,ad)
                        exact=[[e,l,l+len(frag)] for e,l,frag in pieces]
                        expect=[n,len(text.encode()),exact,hashlib.sha256(text.encode()).hexdigest()]
                        assert expect==record["paid"][str(cap)]
                        counts["exact_serialization"]+=1
                    if kind not in ("merged","short"):continue
                    if a=="ratio" and kind=="short":
                        short=pieces
                        scope["non_ascii_questions"]+=int(any(not s.isascii() for _,_,s in pieces))
                        scope["supplementary_questions"]+=int(any(any(ord(ch)>65535 for ch in s) for _,_,s in pieces))
                        scope["embedded_header_pattern_questions"]+=int(any(re.search(r"(?:^|\n)\[\d+:\d+\] ",s) for _,_,s in pieces))
                    wins=windows(tok,pieces);ranking=order(wins,question)
                    if not wins:
                        primary=[-1,0,0,0];assert all(z==primary for k,z in factors[q]["read"].items() if k.startswith(f"{a}/{kind}/"))
                        continue
                    for anchor,pos in (("anchor",0),("lex",ranking[0])):
                        field=wins[pos][0];same=[j for j in range(len(wins)) if wins[j][0]==field]
                        offsets={"first":same[0],"lex":next(j for j in ranking if j in same)}
                        for step,j in offsets.items():
                            e,l,_=wins[j];actual=next_read(tok,body,e,l,stored)
                            assert factors[q]["read"][f"{a}/{kind}/{anchor}/{step}"]==actual
                            if (anchor,step) in (("anchor","first"),("lex","lex")):
                                old="first" if anchor=="anchor" else "bm25"
                                assert opens[q]["read"][f"{a}/{kind}/{old}"]==actual
                                counts["open_vs_whole_field_tokenization"]+=1
                            counts["factor_vs_whole_field_tokenization"]+=1
            assert short is not None
            joined=reconstruct(short)
            text,n,parts=payload(tok,joined,"short",2048,ad);rec=recv[q]
            assert n==rec["tokens_internal"] and [[e,l,l+len(s)] for e,l,s in parts]==rec["shown"]
            wins=windows(tok,parts);ranking=order(wins,question)
            actual=next_read(tok,body,*wins[ranking[0]][:2],stored) if wins else [-1,0,0,0]
            assert actual==rec["opened"];counts["receiver_full_reconstruction"]+=1
            distinct_bytes+=sum(len(body[e][l:].encode()) for e,l in stored)
    assert counts["questions"]==len(wanted)
    # A literal text stream is not injective over structured records.
    A=[(7,0,"abc\n[8:4] xyz")];B=[(7,0,"abc"),(8,4,"xyz")]
    v1=payload(tok,A,"short",2048,{});v2=payload(tok,B,"short",2048,{})
    assert v1[:2]==v2[:2] and v1[2]!=v2[2]
    sample="é e\u0301 Ж 中 𐍈 🤖\r\nعَرَبِيّ "+("word "*300)
    checks=0
    for begin in (0,2,5,8):
        for cap in (3,7,16,31,128):
            s,n=clipped(tok,sample[begin:],cap)
            assert n==len(tok.encode(s,add_special_tokens=False).ids)<=cap and sample[begin:begin+len(s)]==s;checks+=1
    save(D/"token-audit.json",{"counts":counts,"scope":scope,"bytes_of_distinct_whole_suffixes_crosschecked_with_progressive_tokenizer":distinct_bytes,
        "constructed_unicode_cases":checks,"constructed_short_header_ambiguity":True,"sample":sha(D/"sample.json"),"tokenizer":sha(TOK),"code":sha(__import__('pathlib').Path(__file__))})
if __name__=="__main__":main()

