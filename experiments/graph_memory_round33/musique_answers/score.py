"""Apply the published MuSiQue AnswerMetric to sealed span predictions."""
import sys,re
from collections import defaultdict
from reader import HERE,PRIVATE,SOURCE,PRIOR,MODEL,ARMS,Tokenizer,np,sha,get,put,hashlib,json,encode_doc
AUTHOR=SOURCE.parent/"author"
sys.path.insert(0,str(AUTHOR))
from metrics.answer import AnswerMetric,normalize_answer,compute_exact,compute_f1
def ref_contains(needle,body):
    return bool(needle and (" "+needle+" ") in (" "+body+" "))
def interval(weights,delta,salt):
    counts=np.asarray([v[0] for v in weights.values()]);sumdiff=np.asarray([v[1] for v in weights.values()])
    rng=np.random.default_rng(salt);rep=[]
    for _ in range(80):
        ix=rng.integers(0,len(counts),(100,len(counts)))
        rep.extend(100*sumdiff[ix].sum(axis=1)/counts[ix].sum(axis=1))
    return np.quantile(rep,[.025,.975]).tolist()
def run():
    assert sha(HERE/"predictions.json.gz")==get(HERE/"seal.json")["predictions"]
    assert sha(HERE/"plan.json")==get(HERE/"seal.json")["plan"]
    assert sha(SOURCE)==get(HERE/"plan.json")["source"] and sha(PRIVATE/"view.json.gz")==get(HERE/"plan.json")["input_view"]
    view=get(PRIVATE/"view.json.gz");pred=get(HERE/"predictions.json.gz")
    tok=Tokenizer.from_file(str(MODEL/"tokenizer.json"));records={};official={m:AnswerMetric() for m in ARMS}
    with SOURCE.open(encoding="utf8") as fd:
        for line in fd:
            r=json.loads(line);q=r["id"];assert r["answerable"]
            question,docs,arms=view[q];gold=[r["answer"],*r["answer_aliases"]]
            refs={normalize_answer(x) for x in gold if normalize_answer(x)}
            hop=sum(bool(p["is_supporting"]) for p in r["paragraphs"])
            portions={}
            for k,fields in docs.items():
                _,meta=encode_doc(tok,fields)
                portions[k]=[normalize_answer(fields[f][min(x[1] for x in meta if x and x[0]==f):max(x[2] for x in meta if x and x[0]==f)]) for f in range(2) if any(x and x[0]==f for x in meta)]
            key=hashlib.sha256(json.dumps([" ".join(s.lower().split()) for s in docs[str(arms["seed"][0])]],ensure_ascii=False).encode()).hexdigest()
            results={}
            for m in ARMS:
                did,f,l,h,n=pred[q][m];answer=docs[str(did)][f][l:h]
                assert did in arms[m] and 0<=l<h<=len(docs[str(did)][f]) and answer.strip()
                official[m](answer,gold)
                em=max(compute_exact(g,answer) for g in gold);f1=max(compute_f1(g,answer) for g in gold)
                lit=any(ref_contains(x,b) for d in arms[m] for b in portions[str(d)] for x in refs)
                results[m]=[em,f1,n,int(lit),arms[m][-1]]
            records[q]={"hops":hop,"cluster":key,"r":results}
    assert len(records)==2417 and set(pred)==set(records)==set(view)
    def aggregate(sub):
        return {m:dict(zip(("EM","F1","mean_input_tokens","literal_rate"),np.mean([row["r"][m][:4] for row in sub],axis=0))) for m in ARMS}
    def compare(a,b,metric):
        g=defaultdict(lambda:[0,0.]);v=[]
        for k,row in records.items():
            d=row["r"][a][metric]-row["r"][b][metric]
            g[row["cluster"]][0]+=1;g[row["cluster"]][1]+=d;v.append(d)
        return {"pp":100*np.mean(v),"CI95_question":interval({i:[1,x] for i,x in enumerate(v)},v,19806),"CI95_document":interval(g,v,19807),"wins":sum(float(x)>0 for x in v),"losses":sum(float(x)<0 for x in v)}
    sub=list(records.values());scores=aggregate(sub)
    for m in ARMS: assert np.allclose(list(official[m].get_metric()),[scores[m]["EM"],scores[m]["F1"]],atol=1e-13)
    comparisons={a+"-"+b:{tag:compare(a,b,i) for i,tag in [(0,"EM"),(1,"F1")]} for a,b in [("local_static","title"),("local_static","mention_title"),("mention_title","title"),("title","seed")]}
    strata={}
    for key,rows in [(str(k)+"hop",[r for r in sub if r["hops"]==k]) for k in (2,3,4)]+[("choice_differs_title",[r for r in sub if r["r"]["local_static"][-1]!=r["r"]["title"][-1]]),("choice_differs_mention",[r for r in sub if r["r"]["local_static"][-1]!=r["r"]["mention_title"][-1]])]:
        strata[key]={"n":len(rows),"scores":aggregate(rows) if rows else {}}
    put(HERE/"outcomes.json.gz",records)
    put(HERE/"results.json",{"n":len(sub),"documents":len({r["cluster"] for r in sub}),"scores":scores,"contrasts":comparisons,"strata":strata,"author_sha":{k:sha(AUTHOR/"metrics"/(k+".py")) for k in ("metric","answer")},"predict_seal":sha(HERE/"seal.json"),"total_logical_answers":len(sub)*len(ARMS),"unique_reader_calls":sum(len({tuple(v) for v in r[2].values()}) for r in view.values())})
if __name__=="__main__":run()
