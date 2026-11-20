"""Run the authors' Java metric bodies, using the pure-Python fuzzywuzzy default."""
import sys, ast, json, gzip, tarfile, re, math, itertools
from collections import defaultdict,Counter
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D/"eval_deps"))
import numpy as np
from fuzzywuzzy import fuzz
from nltk.tokenize import RegexpTokenizer
from keywordlist import get_language_keywords
from infer_cross import read,save,sha
FIELDS=("em","es","id_em","id_f1")
def upstream():
    scope=dict(re=re,fuzz=fuzz,code_tokenizer=RegexpTokenizer(r"\w+"),get_language_keywords=get_language_keywords)
    for p,picks in [("eval_utils.py",{"IDENTIFIER_REGEX","string_pattern","get_bracket_lang_statement","postprocess_code_lines","remove_comments","extract_identifiers","is_identifier","cal_edit_sim"}),("eval_metric.py",{"process_examples","compute_id_match"})]:
        tree=ast.parse((D/p).read_text(encoding="utf8"))
        def selected(n):
            return isinstance(n,ast.FunctionDef) and n.name in picks or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in picks for t in n.targets)
        body=[n for n in tree.body if selected(n)]
        assert len(body)==len(picks)
        exec(compile(ast.Module(body=body,type_ignores=[]),str(D/p),"exec"),scope)
    scope["parser"]=None
    return scope
def comparisons(ds,a,b):
    X={};rng=np.random.default_rng(2026111851)
    for f in FIELDS:
        groups=defaultdict(list)
        for row in ds:
            d=row["m"][a][f]-row["m"][b][f] if "m" in row else 0
            groups[row["repo"]].append(d)
        mat=np.array([(len(v),sum(v)) for v in groups.values()])
        samples=mat[rng.integers(len(mat),size=(10000,len(mat)))].sum(axis=1)
        v=mat[:,1];nonzero=v[v!=0]
        p=None
        if f in ("em","id_em"):
            if len(nonzero)<=18:
                p=sum(abs(np.dot(s,nonzero))>=abs(v.sum()) for s in itertools.product((-1,1),repeat=len(nonzero)))/2**len(nonzero)
            else:
                p=(1+(np.abs(rng.choice([-1,1],size=(100000,len(nonzero)))@nonzero)>=abs(v.sum())).sum())/100001
        X[f]=dict(diff=float(v.sum()/len(ds)),net=float(v.sum()),wins=sum(x>0 for vv in groups.values() for x in vv),losses=sum(x<0 for vv in groups.values() for x in vv),projects=len(mat),ci=np.quantile(samples[:,1]/samples[:,0],[.025,.975]).tolist(),p=None if p is None else float(p))
    return X
def main(k):
    lock=read(k+"_decisions.json");pack=read(k+"_packets.json.gz");ix=read(k+"_assignment.json")
    for n,h in read(k+"_input_lock.json").items():assert sha((D/n).read_bytes())==h
    for n,h in read(k+"_data_lock.json")["sha"].items():assert sha((D/n).read_bytes())==h
    assert set(lock)=={v+".json.gz" for row in ix.values() for v in row.values()}
    assert all(sha((D/(k+"_calls")/n).read_bytes())==h for n,h in lock.items())
    need={r["id"] for r in pack};up=upstream(); gold={}
    with tarfile.open(D/"crosscodeeval_data.tar.xz") as tf:
        for row in map(json.loads,tf.extractfile("java/line_completion_rg1_unixcoder_cosine_sim.jsonl")):
            i=row["metadata"]["task_id"]
            if i in need:gold[i]=dict(prompt=row["prompt"],groundtruth=row["groundtruth"])
    assert len(gold)==len(pack)
    items=[];calls={}
    for x in pack:
        i=x["id"];methods={}
        for a,h in ix[i].items():
            if h not in calls:calls[h]=read(k+"_calls/"+h+".json.gz")["reply"]
            resp=calls[h];msg=resp["choices"][0]["message"]["content"] or ""
            if msg.startswith(chr(96)*3):msg="\n".join(msg.split("\n")[1:]).strip(chr(96))
            s,em=up["process_examples"]("java",({"task_id":i,"pred":msg},gold[i]))
            tp,fp,fn=up["compute_id_match"](s["pred_ids"],s["target_ids"])
            methods[a]=dict(em=em,es=up["cal_edit_sim"]([s["target"]],[s["pred"]]),id_em=int(s["target_ids"]==s["pred_ids"]),id_f1=(2*tp/(2*tp+fp+fn)) if tp+fp+fn else 0.,pred=s["pred"],gold=s["target"],prompt_tokens=resp["usage"]["prompt_tokens"],reply_tokens=resp["usage"]["completion_tokens"])
        items.append(dict(id=i,repo=x["repo"],m=methods,changed=ix[i]["order"]!=ix[i]["bridge"]))
    save(k+"_items.json.gz",items)
    arms=list(items[0]["m"])
    means={a:{f:float(np.mean([z["m"][a][f] for z in items])) for f in (*FIELDS,"prompt_tokens","reply_tokens")} for a in arms}
    res=dict(metrics=means,counts={a:sum(z["m"][a]["em"] for z in items) for a in arms},physical_calls=len(calls),tokens={f:sum(v["usage"][f] for v in calls.values()) for f in ["prompt_tokens","completion_tokens"]},n=len(items),changed=sum(z["changed"] for z in items))
    if k=="D":
        res["bridge_order"]=comparisons(items,"bridge","order")
        res["official_empty"]=comparisons(items,"official","empty")
    else:
        pop=read("E_population.json.gz");lookup={x["id"]:x for x in items}
        for z in pop:
            assert z["changed"]==(z["id"] in lookup)
            if z["changed"]:z["m"]=lookup[z["id"]]["m"]
        for name,sub in [("usable",[z for z in pop if z["eligible"]]),("unseen",[z for z in pop if z["eligible"] and not z["known"]]),("active",items)]:
            res[name]=dict(n=len(sub),contrast=comparisons(sub,"bridge","order"))
    save(k+"_results.json",res);print(k,res["counts"],res["physical_calls"],flush=True)
if __name__=="__main__":main(sys.argv[1])

