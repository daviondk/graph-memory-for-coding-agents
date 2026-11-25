from common28 import *
import io,struct,sys,tokenize
from time import perf_counter_ns
sys.path.insert(0,str(R))
from predict import lexical_blocks
from tokenizers import Tokenizer
from operators import anchors
def text_of(key):
    blob=(P/"files"/key).read_bytes()
    return io.TextIOWrapper(io.BytesIO(blob),encoding=tokenize.detect_encoding(io.BytesIO(blob).readline)[0],newline=None).read()
def main(panel):
    checks();inp=read(D/(panel+"-dataset.json"));assert sha(D/(panel+"-inputs.json.gz"))==inp["inputs"]
    qpath=P/(panel+"-queries.json");assert sha(qpath)==inp["queries"];queries=read(qpath)
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding()
    ids=lambda s:tok.encode(s,add_special_tokens=False).ids
    result=[];skips=[]
    for row in read(D/(panel+"-inputs.json.gz")):
        key=row["file"];q=row["issue"];assert sha(P/"files"/key)==row["sha"]
        txt=text_of(key);lines=txt.split("\n");t0=perf_counter_ns()
        e=[0];tokens=[]
        for line in lines:tokens+=ids(line);e.append(len(tokens))
        assert tokens==ids(txt);tindex=perf_counter_ns()-t0
        t0=perf_counter_ns();order=lexical_blocks(lines,queries[q],e);tbm=perf_counter_ns()-t0
        if not order:skips.append([q,"empty_file"]);continue
        lo,hi=order[0]
        try:addr,info=anchors(txt,lines,(lo,hi),order,queries[q])
        except (IndentationError,SyntaxError,tokenize.TokenError) as ex:
            skips.append([q,"lexical_error",type(ex).__name__]);continue
        delays={k:info.pop(k) for k in ("observed_ns","build_ns","lazy_ns","lookup_ns")}
        def opened(line,cap):
            if line is None or line>len(lines):return dict(span=[],cost=0,wire=digest(""))
            a=e[line-1];head=ids(f"[0:{a}]");b=min(len(tokens),a+max(0,cap-len(head)))
            if b<=a:return dict(span=[],cost=0,wire=digest(""))
            wire=head+tokens[a:b]
            return dict(span=[a,b],cost=len(wire),wire=hashlib.sha256(struct.pack("<"+"I"*len(wire),*wire)).hexdigest())
        arms={k:opened(v,256) for k,v in addr.items()}
        cap=min(arms[k]["cost"] for k in ("query_call","repeat_bm25"))
        while True:
            equal={k:opened(addr[k],cap) for k in ("query_call","repeat_bm25")}
            c=[x["cost"] for x in equal.values()]
            if min(c)==max(c):break
            assert min(c)<cap;cap=min(c)
        result.append(dict(issue=q,file=key,repo=row["repo"],first=[lo,hi],visible=[e[lo-1],e[hi]],address=addr,arms=arms,equal=equal,info=info,timing=dict(line_token_ns=tindex,bm25_ns=tbm,**delays)))
    save(D/(panel+"-forecasts.json.gz"),result)
    save(D/(panel+"-seal.json"),dict(n=len(result),dataset=sha(D/(panel+"-dataset.json")),forecasts=sha(D/(panel+"-forecasts.json.gz")),operators=sha(D/"operators.py"),runner=sha(D/"predict28.py"),exclusions=skips))
    print(panel,"signed forecasts",len(result),"skips",skips)
if __name__=="__main__":main(sys.argv[1])

