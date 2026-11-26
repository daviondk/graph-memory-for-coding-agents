"""Freeze outgoing author links on the exact first read. No task annotations are opened."""
from bisect import bisect_left
from collections import Counter,defaultdict
from functools import lru_cache
from urllib.parse import unquote
from tokenizers import Tokenizer
from common import *

def destination(s):
    if not isinstance(s,str) or not s or "://" in s or s.startswith(("/","//")):return ""
    return title(unquote(s.split("#",1)[0],errors="strict"))

def inspect_source(record,opened,full,titles,ids,seed):
    source_id,sentences,mentions=record
    body=" ".join(sentences)
    canon=compact(body);snippet=compact(opened)
    if not snippet or not canon.startswith(snippet):return None
    starts=[];pos=0
    for sent in sentences:
        starts.append(pos);pos+=len(sent)+1
    # Coordinates map the half-open visible non-whitespace prefix back to the source.
    chars=[i for i,c in enumerate(body) if not c.isspace()]
    end=chars[len(snippet)-1]+1
    direct=set();resolved=set();evidence=[];valid=0;outside=0
    for m in mentions:
        j,a,b=m.get("sent_idx"),m.get("start"),m.get("end")
        if not all(isinstance(x,int) for x in (j,a,b)) or not (0<=j<len(sentences) and 0<=a<b<=len(sentences[j])):
            return {"invalid":True}
        anchor=sentences[j][a:b]
        if not compact(anchor):return {"invalid":True}
        start,stop=starts[j]+a,starts[j]+b
        if stop>end:
            outside+=1
            continue
        valid+=1
        try:dest=destination(m["ref_url"])
        except (UnicodeError,KeyError):return {"invalid":True}
        matches=[k for k,t in enumerate(titles) if t==dest]
        names=set(matches);ref_ids=set(map(str,m.get("ref_ids") or []))
        id_hits={i for i,t in enumerate(titles) if len(ids.get(t,[]))==1 and next(iter(ids[t])) in ref_ids}
        if len(names)==1 and seed not in names:direct.update(names)
        if len(names)==1 and ref_ids:
            k=next(iter(names));registry=ids.get(titles[k],[])
            if len(registry)==1 and registry[0] not in ref_ids:continue
        combined=names|id_hits
        if len(combined)!=1 or seed in combined:continue
        k=next(iter(combined))
        if not names and len(ref_ids)!=1:continue
        resolved.add(k)
        evidence.append([k,j,a,b,stop,end,textsha(anchor),textsha(dest),sorted(ref_ids),int(bool(names)),int(bool(id_hits))])
    return {"source":str(source_id),"direct":sorted(direct),"href":sorted(resolved),"prefix_literal":body.startswith(opened),
            "full_literal":body==full,"full_whitespace":canon==compact(full),"visible_refs":valid,"outside_refs":outside,"witness":evidence}

def run():
    source=read(D/"source.json");docfile=PRIVATE/"sources.json.gz";idfile=PRIVATE/"titles.json.gz"
    assert sha(docfile)==source["selected_sources"] and sha(idfile)==source["selected_ids"]
    docs=read(docfile);ids=read(idfile)
    tf=W.parents[1]/"x20-r23-multidoc2dial/model/tokenizer.json";tok=Tokenizer.from_file(str(tf))
    receipts={}
    for split,study in CONFIG.items():
        st=D.parent/study;view=read(visible(split));orders=read(st/"orders.json.gz")
        assert sha(st/"orders.json.gz")==read(st/"retrieval-seal.json")["orders"]
        rows={}
        for q,(_,catalog) in view.items():
            old=orders[q];seed,sort=old["seed"],old["order"];full=catalog[seed][2]
            assert sorted(sort+[seed])==list(range(len(catalog)))
            titles=[title(t) for _,t,_ in catalog];key=titles[seed]
            offsets=tok.encode(full,add_special_tokens=False).offsets[:192]
            opened=full[:offsets[-1][1]] if offsets else ""
            results=[inspect_source(z,opened,full,titles,ids,seed) for z in docs.get(key,[])]
            valid=[z for z in results if z is not None]
            status="ok";data=None
            if not results:status="source_title_absent"
            elif not valid:status="visible_prefix_differs"
            elif any(r.get("invalid") for r in valid):status="invalid_annotation"
            elif len({(tuple(r["href"]),tuple(r["direct"])) for r in valid})!=1:status="ambiguous_edges"
            else:data=valid[0]
            href=data["href"] if data else [];direct=data["direct"] if data else []
            text=sorted(map(int,old["edges"]));lex=sort[0]
            def choose(target):return next((i for i in sort if i in target),lex)
            original=choose(text);assert original==old["true"] and lex==old["lex"]
            cluster=textsha(catalog[seed][1]+"\0"+full)
            literal=bool(valid and status=="ok" and all(v["prefix_literal"] for v in valid))
            rows[q]={"seed":seed,"sort":sort,"text_edges":text,"href_edges":href,"direct_edges":direct,"status":status,
                     "title_candidates":len(results),"compatible":len(valid),"prefix_literal":literal,
                     "full_literal":bool(data and all(r["full_literal"] for r in valid)),
                     "full_whitespace":bool(data and all(r["full_whitespace"] for r in valid)),
                     "visible_refs":data["visible_refs"] if data else 0,"beyond_prefix":data["outside_refs"] if data else 0,
                     "witness":data["witness"] if data else [],"source_ids":sorted({r["source"] for r in valid if "source" in r}),
                     "cluster":cluster,"prefix_sha":textsha(opened),"chars":len(opened),
                     "choices":{"text":original,"lex":lex,"href":choose(href),"direct":choose(direct),
                                "literal":choose(href) if literal else lex,"union":choose(set(text)|set(href))}}
        f=D/f"forecast-{split}.json.gz";write(f,rows)
        receipts[split]={"rows":len(rows),"predictions":sha(f),"orders":sha(st/"orders.json.gz"),"view":sha(visible(split)),"tokenizer":sha(tf)}
        print(split,Counter(r["status"] for r in rows.values()),flush=True)
    write(D/"prediction_seal.json",{"subsets":receipts,"source":sha(D/"source.json"),"code":sha(Path(__file__)),"protocol":sha(D/"PROTOCOL_RU.md")})

if __name__=="__main__":run()

