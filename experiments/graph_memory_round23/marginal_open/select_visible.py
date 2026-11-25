"""Choose windows using only private visible text, field lengths and the pure policy."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter_ns
import sqlite3
from tokenizers import Tokenizer
from common import D,PRIVATE,TOK,read,save,sha,check_plan
from novelty import make_windows,lexical_order,choose

def shard(i):
    src=PRIVATE/f"visible-{i}.json.gz";seal=read(D/"visible-seal.json")
    assert sha(src)==seal["parts"][i]["visible"] and sha(D/"field-lengths.sqlite")==seal["catalog"] and sha(TOK)==seal["tokenizer"]
    db=sqlite3.connect((D/"field-lengths.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True);tok=Tokenizer.from_file(str(TOK))
    out=[]
    for r in read(src):
        q,t=r["q"],r["t"];visible=defaultdict(list);lens={};header={}
        tic=perf_counter_ns()
        for e,l,s in r["fragments"]:visible[e].append((l,l+len(s)))
        for e in visible:lens[e]=db.execute("select n from field_size where t=? and e=?",(t,e)).fetchone()[0]
        field_ns=perf_counter_ns()-tic;start=perf_counter_ns()
        wins=make_windows(r["fragments"],tok);order=lexical_order(r["question"],wins)
        rank_ns=perf_counter_ns()-start;start=perf_counter_ns()
        for w in wins:
            if (w.field,w.start) not in header:header[w.field,w.start]=len(tok.encode(f"[{w.field}:{w.start}] ",add_special_tokens=False).ids)
        ranks={j:k for k,j in enumerate(order)}
        picks,detail=choose(wins,order,visible,lens,[header[w.field,w.start] for w in wins],256)
        policy_ns=perf_counter_ns()-start;routes={}
        for arm,j in picks.items():
            if j is None:routes[arm]=None;continue
            w=wins[j];routes[arm]=[w.field,w.start,w.end,w.tokens,ranks[j],*detail[j]]
        out.append({"q":q,"t":t,"paid_in":r["paid"],"wire":r["wire"],"n_windows":len(wins),"n_visible_fields":len(lens),"eligible_windows":sum(new>0 for end,new,width in detail),"picks":routes,"cost_ns":[field_ns,rank_ns,policy_ns]})
    db.close();p=D/f"picks-{i}.json.gz";save(p,out);return [p.name,sha(p),len(out)]
def main():
    check_plan()
    with ProcessPoolExecutor(2) as ex:rows=list(ex.map(shard,range(8)))
    assert sum(r[2] for r in rows)==2000
    save(D/"choice-seal.json",{"parts":rows,"visible":sha(D/"visible-seal.json"),"plan":sha(D/"plan.json"),"policy":sha(D/"novelty.py"),"code":sha(__import__("pathlib").Path(__file__))})
if __name__=="__main__":main()

