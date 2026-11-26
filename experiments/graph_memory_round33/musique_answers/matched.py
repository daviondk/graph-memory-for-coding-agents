"""Offline equal-realized-token counterfactual on the fixed retrieval outputs."""
import sys
from collections import defaultdict
from reader import *
from score import AnswerMetric,compute_f1,compute_exact,interval

def predict_matched():
    plan=get(HERE/"plan.json");ref=get(HERE/"predictions.json.gz")
    assert sha(HERE/"predictions.json.gz")==get(HERE/"seal.json")["predictions"] and sha(PRIVATE/"view.json.gz")==plan["input_view"]
    cfg={"protocol":sha(HERE/"MATCHED_PROTOCOL_RU.md"),"code":sha(Path(__file__)),"parent":sha(HERE/"seal.json"),"model":sha(MODEL/"model_quantized.onnx"),"tok":sha(MODEL/"tokenizer.json")}
    assert cfg["model"]==plan["model"] and cfg["tok"]==plan["tokenizer"] and ort.__version__==plan["runtime"]
    put(HERE/"matched-plan.json",cfg)
    view=get(PRIVATE/"view.json.gz");tok=Tokenizer.from_file(str(MODEL/"tokenizer.json"))
    opt=ort.SessionOptions();opt.intra_op_num_threads=2;opt.inter_op_num_threads=1;opt.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    engine=ort.InferenceSession(str(MODEL/"model_quantized.onnx"),sess_options=opt,providers=["CPUExecutionProvider"])
    out={};recomputed=0;reused=0
    for qid,(question,docs,arms) in view.items():
        encoded={k:encode_doc(tok,v) for k,v in docs.items()};q=tok.encode(question,add_special_tokens=False).ids[:64]
        second={str(arms[m][1]) for m in ARMS[1:]};target=min(len(encoded[s][0]) for s in second)
        cache={}
        for m in ARMS[1:]:
            k=str(arms[m][1])
            if k in cache:continue
            if len(encoded[k][0])==target: cache[k]=ref[qid][m];reused+=1
            else:
                enc=dict(encoded);enc[k]=tuple(v[:target] for v in encoded[k])
                cache[k]=predict(q,arms[m],enc,engine,tok);recomputed+=1
        out[qid]={m:cache[str(arms[m][1])] for m in ARMS[1:]}
        assert len({v[-1] for v in out[qid].values()})==1
    put(HERE/"matched-predictions.json.gz",out)
    put(HERE/"matched-seal.json",{"prediction":sha(HERE/"matched-predictions.json.gz"),"plan":sha(HERE/"matched-plan.json"),"recomputed":recomputed,"reused":reused})
def score_matched():
    seal=get(HERE/"matched-seal.json");assert seal["prediction"]==sha(HERE/"matched-predictions.json.gz")
    view=get(PRIVATE/"view.json.gz");pred=get(HERE/"matched-predictions.json.gz");orig=get(HERE/"outcomes.json.gz");out={}
    aggregates={m:AnswerMetric() for m in ARMS[1:]}
    with SOURCE.open(encoding="utf8") as fd:
        for line in fd:
            row=json.loads(line);q=row["id"];question,docs,arms=view[q]
            record={};refs=[row["answer"],*row["answer_aliases"]]
            for m in ARMS[1:]:
                doc,f,l,h,n=pred[q][m];s=docs[str(doc)][f][l:h];assert doc in arms[m] and s.strip()
                aggregates[m](s,refs);record[m]=[max(compute_exact(g,s) for g in refs),max(compute_f1(g,s) for g in refs),n]
            out[q]=record
    comparisons={}
    for b in ("title","mention_title"):
        v=[r["local_static"][1]-r[b][1] for r in out.values()];g=defaultdict(lambda:[0,0.])
        for q,d in zip(out,v):
            node=g[orig[q]["cluster"]];node[0]+=1;node[1]+=d
        comparisons[b]={"pp":100*np.mean(v),"CI95_document":interval(g,v,24215),"CI95_question":interval({i:[1,x] for i,x in enumerate(v)},v,24216),"wins":sum(x>0 for x in v),"losses":sum(x<0 for x in v)}
    put(HERE/"matched-outcomes.json.gz",out)
    put(HERE/"matched-results.json",{"means_EM_F1":{k:v.get_metric() for k,v in aggregates.items()},"contrasts_F1":comparisons,"questions":len(out),"equal_per_question":all(len({v[2] for v in r.values()})==1 for r in out.values()),"mean_tokens":np.mean([r["title"][2] for r in out.values()]),"seal":sha(HERE/"matched-seal.json")})
if __name__=="__main__":predict_matched();score_matched()
