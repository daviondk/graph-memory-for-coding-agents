"""Generate opaque graph projections. Only whitelisted faulty-trace fields reach the predictor."""
from pathlib import Path
from hashlib import sha256
import gzip,json,re,sys
OUT=Path(__file__).resolve().parent
PRIV=Path("D:/CodexResearch/x20-r29-selective")
PRE=OUT.parent/"rollback_native"
sys.path.insert(0,str(PRE))
from controls import SRC, readl, getcase, save, get

def hashid(x):
    return sha256(x.encode()).hexdigest()[:24]

def project(panel,root):
    observations=[];mapping=[]
    for reg in readl(root/"registry.jsonl"):
        task=reg["task_id"];qid=hashid(panel+"_"+task)
        mem,steps=getcase(root,reg)
        def enc(x): return hashid(qid+"."+x)
        def ids(x):return [enc(a) for a in x or ()]
        def plain(x):
            return re.sub(r"\b(?:m_f?\d+|s_\d+|user_input_\d+)\b"," ",str(x),flags=re.I)
        ms=[dict(id=enc(x["memory_id"]),parents=ids(x.get("derived_from")),text=plain(x["content"])) for x in mem]
        ss=[dict(id=enc(x["step_id"]),type=x["step_type"],parents=ids(x.get("used_ids")),writes=ids(x.get("generated_memory_ids")),text=plain(x["content"]) if x["step_type"]=="claim" else "") for x in steps]
        assert len(ms)==len({x["id"] for x in ms}) and len(ss)==len({x["id"] for x in ss})
        observations.append(dict(id=qid,memory=ms,steps=ss,diagnosis=ids(reg["faulty_memory_ids"])))
        mapping.append(dict(id=qid,task=task,domain=reg["domain"],node={enc(x):x for x in [m["memory_id"] for m in mem]+[s["step_id"] for s in steps]}))
    return observations,mapping
if __name__=="__main__":
    PRIV.mkdir(exist_ok=True)
    rec={}
    for p,sub in (("controlled","controlled_benchmark"),("adapted","adapted_lmev2_subset")):
        obs,m=project(p,SRC/"data"/sub)
        rec[p]=dict(n=len(m),observations=save(PRIV/(p+"-blind.json.gz"),obs),mapping=save(PRIV/(p+"-evaluation-key.json.gz"),m),domains=save(PRIV/(p+"-folds.json"),{x["id"]:x["domain"] for x in m}))
    save(OUT/"input-receipt.json",rec)

