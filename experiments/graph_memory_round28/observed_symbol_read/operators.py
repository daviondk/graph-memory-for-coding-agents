"""Address proposals see a first block, issue text and same-source symbols; no labels."""
from collections import Counter,defaultdict
from functools import lru_cache
import io,keyword,re,token,tokenize
from time import perf_counter_ns
NAME=re.compile(r"[A-Za-z_]\w*")
STOP=set("get set new old add run use used uses make makes value values return returns test tests data none true false self cls type class function method module object list dict str int args kwargs input output file files string change code line call error".split())
def parts(name):
    split=re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"," ",name)
    return {s.lower() for s in re.findall(r"[A-Za-z]+",split) if len(s)>=3 and s.lower() not in STOP}
def name_tokens(content):
    out=[];failed=False
    try:
        for x in tokenize.generate_tokens(io.StringIO("(\n"+content+"\n)").readline):
            if x.type in (token.NAME,token.OP,token.STRING,token.NUMBER):out.append((x.type,x.string,x.start[0]-1))
    except (tokenize.TokenError,IndentationError,SyntaxError):failed=True
    return out,failed
def observations(content):
    lex,failed=name_tokens(content)
    ids=[];calls=[]
    for i,(ty,s,l) in enumerate(lex):
        if ty!=token.NAME or keyword.iskeyword(s) or s in {"self","cls"}:continue
        if i and lex[i-1][1] in {"def","class"}:continue
        ids.append(s)
        if i+1<len(lex) and lex[i+1][1]=="(":calls.append(s)
    return ids,calls,failed
def declarations(text,wanted=None):
    out=defaultdict(list);last=None
    if wanted is not None and not wanted:return out
    for x in tokenize.generate_tokens(io.StringIO(text).readline):
        if x.type==token.NAME and last in {"def","class"} and (wanted is None or x.string in wanted):
            out[x.string].append(x.start[0])
        if x.type not in {token.COMMENT,tokenize.NL,token.INDENT,token.DEDENT}:last=x.string
    return out
def elapsed(f):
    start=perf_counter_ns();ans=f();return ans,perf_counter_ns()-start
def anchors(text,lines,bounds,order,query):
    lo,hi=bounds;first=lo;repeat=order[1][0] if len(order)>1 else None
    local="\n".join(lines[lo-1:hi])
    (observed,calls,trunc),vis_ns=elapsed(lambda:observations(local))
    mapping,index_ns=elapsed(lambda:declarations(text))
    wanted=set(observed)
    small,lazy_ns=elapsed(lambda:declarations(text,wanted))
    gate_lookup,lookup_ns=elapsed(lambda:{w:mapping[w] for w in wanted if w in mapping})
    assert dict(small)==gate_lookup
    qparts=set().union(*(parts(n) for n in NAME.findall(query))) if query else set()
    def distance(i):return max(lo-i,i-hi,0)
    def options(seq,gate):
        count=Counter(seq);orig={}
        for i,n in enumerate(seq):orig.setdefault(n,i)
        rows=[]
        for n,index in orig.items():
            locations=[l for l in small.get(n,()) if not lo<=l<=hi]
            if not locations:continue
            best=min(locations,key=lambda x:(distance(x),x));shared=len(qparts.intersection(parts(n)))
            if gate and not shared:continue
            rows.append((-shared,-count[n],index,distance(best),best,n))
        return sorted(rows)
    opts=options(calls,True);allcalls=options(calls,False);names=options(observed,True)
    target=opts[0][-2] if opts else repeat;symbol=opts[0][-1] if opts else None
    baseline=next((min((l for l in small[n] if not lo<=l<=hi),key=lambda l:(distance(l),l)) for n in calls if n in small and any(not lo<=l<=hi for l in small[n])),repeat)
    chosen={"repeat_bm25":repeat,"right":hi+1 if hi<len(lines) else None,"query_call":target,"goto_first":baseline,"call_unconditional":allcalls[0][-2] if allcalls else repeat,"query_name":names[0][-2] if names else repeat}
    selected=sorted({l for vec in mapping.values() for l in vec if not lo<=l<=hi})
    if symbol:
        j=selected.index(target)
        chosen["rewired"]=selected[(j+max(1,len(selected)//2))%len(selected)]
        pat=re.compile(r"(?<!\w)"+re.escape(symbol)+r"(?!\w)")
        occurrences=[i for i,l in enumerate(lines,1) if not lo<=i<=hi and pat.search(l)]
        chosen["literal"]=min(occurrences,key=lambda i:(distance(i),i)) if occurrences else repeat
    else:chosen.update(rewired=repeat,literal=repeat)
    names_in_query=[n for n in NAME.findall(query) if n in mapping]
    chosen["query_def"]=next((min((l for l in mapping[n] if not lo<=l<=hi),key=lambda l:(distance(l),l)) for n in names_in_query if any(not lo<=l<=hi for l in mapping[n])),repeat)
    return chosen,dict(call_names=len(set(calls)),visible_names=len(wanted),matching_call_names=len(allcalls),gated_names=len(opts),edge=bool(symbol),symbol=symbol,target=target,rewire_same=bool(symbol and chosen["rewired"]==target),partial_lexer=trunc,definitions=sum(len(v) for v in mapping.values()),signature_names=len(mapping),lazy_names=len(small),observed_ns=vis_ns,build_ns=index_ns,lazy_ns=lazy_ns,lookup_ns=lookup_ns)

