from io24 import D,R,read,save,check,sha
from selector import besl,selftest
from open24 import apply
from pathlib import Path
import sys,runpy
sys.path.insert(0,str(R/"open_transfer"))
from run import c,merged,paid_open
def select():
    check();selftest();tok=c.tok();view=c.get_views();docs=view["documents"]
    lengths={i:len(d[2]) for i,d in enumerate(docs)};qtext={q:(t,x) for q,t,x in view["q"]}
    src=R/"transfer/predictions.json.gz";p=R/"marginal_transfer/actions.json.gz"
    assert sha(p)==read(R/"marginal_transfer/forecast-seal.json")["predictions"] and sha(src)==read(R/"transfer/forecast-seal.json")["forecasts"]
    previous=read(p);rows={}
    for r in read(src):
        q=r["q"];t,x=qtext[q];a=r["arms"]["two_ratio"];parts=[view["blocks"][j] for j in a["chosen"]]
        assert c.sha("\n".join(c.render(z,docs) for z in parts).encode())==a["text_sha"]
        base=merged([(z["doc"],z["a"],z["b"]) for z in parts]);frag=[(e,l,docs[e][2][l:h]) for e,l,h in base]
        picks,stats=besl(x,frag,{e:lengths[e] for e,l,s in frag},tok);old=previous.pop(q)
        assert base==old["base"] and t==r["dialogue"]
        for k in ("bm25","first_positive","rank_novelty"):
            ob=old["actions"][k];assert picks[k]==([ob[0],ob[1][0],ob[1][1]] if ob else None)
        rows[q]={"t":t,"base":base,"picks":picks,"stats":stats}
    assert len(rows)==661 and not previous
    h=save(D/"mdd-choices.json.gz",rows);save(D/"mdd-choice-seal.json",{"choices":h,"selector":sha(D/"selector.py"),"code":sha(Path(__file__)),"plan":sha(D/"plan.json")})
def execute():
    lock=read(D/"mdd-choice-seal.json");p=D/"mdd-choices.json.gz";assert sha(p)==lock["choices"]
    docs=c.get_views()["documents"];tok=c.tok()
    vals={q:apply(r["picks"],lambda e:docs[e][2],paid_open,tok) for q,r in read(p).items()}
    h=save(D/"mdd-opened.json.gz",vals);save(D/"mdd-open-seal.json",{"actions":h,"choices":sha(D/"mdd-choice-seal.json"),"engine":sha(D/"open24.py"),"upstream_paid":sha(R/"field_first/decide.py")})
def targets(picks):
    f=runpy.run_path(str(R/"transfer/score.py"),run_name="score_source")
    g,issues=f["labels"](c.get_views());assert not issues and set(g)==set(picks)
    return {q:sp[0] for q,sp in g.items()}
if __name__=="__main__":globals()[sys.argv[1]]()
