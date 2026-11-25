from io24 import D,R,W,read,save,check,sha
from selector import besl,selftest
from open24 import apply
import sqlite3,sys
from collections import defaultdict
from tokenizers import Tokenizer
sys.path.insert(0,str(R/"marginal_open"))
from common import PRIVATE,TOK
from execute import paid,CACHE
from verify import db,ids,gold_ranges

def select():
    check();selftest();tok=Tokenizer.from_file(str(TOK));old=R/"marginal_open"
    cat=db(old/"field-lengths.sqlite");rows={}
    for i,part in enumerate(read(old/"visible-seal.json")["parts"]):
        private=PRIVATE/f"visible-{i}.json.gz";assert sha(private)==part["visible"]
        name,h,_=read(old/"choice-seal.json")["parts"][i];assert sha(old/name)==h
        oldp={r["q"]:r["picks"] for r in read(old/name)}
        for r in read(private):
            q,t=r["q"],r["t"];frag=r["fragments"]
            shape={e:cat.execute("select n from field_size where t=? and e=?",(t,e)).fetchone()[0] for e in {f[0] for f in frag}}
            picks,stats=besl(r["question"],frag,shape,tok);prev=oldp.pop(q)
            for k in ("bm25","first_positive","rank_novelty"):assert (picks[k][1:] if picks[k] else None)==(prev[k][:2] if prev[k] else None)
            rows[q]={"t":t,"shard":i,"base":[[e,l,l+len(s)] for e,l,s in frag],"picks":picks,"stats":stats}
        assert not oldp
    cat.close();assert len(rows)==2000
    save(D/"ise-choices.json.gz",rows);save(D/"ise-choice-seal.json",{"choices":sha(D/"ise-choices.json.gz"),"selector":sha(D/"selector.py"),"code":sha(__import__("pathlib").Path(__file__)),"plan":sha(D/"plan.json")})
def execute():
    s=read(D/"ise-choice-seal.json");p=D/"ise-choices.json.gz";assert sha(p)==s["choices"]
    reg=db(R/"read_causes/registry.sqlite");by=defaultdict(list);tok=Tokenizer.from_file(str(TOK))
    for q,r in read(p).items():by[r["shard"],r["t"]].append((q,r))
    rows={}
    for (i,t),records in by.items():
        src=read(CACHE/f"{i}-{t}.json.gz")["fields"];lookup=dict(reg.execute("select e,eid from address where t=?",(t,)))
        for q,r in records:rows[q]=apply(r["picks"],lambda e:src[lookup[e]],paid,tok)
    reg.close();h=save(D/"ise-opened.json.gz",rows);save(D/"ise-open-seal.json",{"actions":h,"choices":sha(D/"ise-choice-seal.json"),"engine":sha(D/"open24.py"),"upstream_paid":sha(R/"marginal_open/execute.py")})
def targets(picks):
    gold=read(W/"graph_memory_round18/isetrace_official/gold-spans.json.gz");reg=db(R/"read_causes/registry.sqlite")
    ans={q:gold_ranges(gold[q],ids(reg,r["t"])) for q,r in picks.items()};reg.close();return ans
if __name__=="__main__":globals()[sys.argv[1]]()
