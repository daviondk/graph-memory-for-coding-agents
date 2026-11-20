"""After predictions have been saved. Runs upstream metric (NumPy 2 convenience shim)."""
import csv,sys,hashlib,json,collections,math,random
from pathlib import Path
import numpy as np
src,ranksfile,outdir,metricdir=map(Path,sys.argv[1:5])
sys.path.insert(0,str(metricdir.resolve()))
if not hasattr(np,'asfarray'):np.asfarray=lambda obj:np.asarray(obj,dtype=float)
from official_retrieval import evaluate_retrieval
data=json.loads(src.read_text(encoding='utf8')); preds=[json.loads(l) for l in (outdir/'predictions.jsonl').read_text(encoding='utf8').splitlines()]
ranked={r['question_id']:r for line in ranksfile.read_text(encoding='utf8').splitlines() if (r:=json.loads(line))}
assert len(preds)==len(data)==500
methods=list(preds[0]['orders'])
scored=[]; by={}
for i,(p,q) in enumerate(zip(preds,data)):
    assert p['row']==i
    ids=q['haystack_session_ids']; gold=q['answer_session_ids'];qid=q['question_id']
    if qid.endswith('_abs'):
        # Official suffix defines abstention. Some rows retain source history IDs.
        continue
    assert gold
    rankids=ranked[qid]['top20_session_ids']; full=[ids.index(s) for s in rankids]
    row={'row':i,'id':qid,'type':q['question_type'],'size':len(set(gold)),'eligible':p['eligible'],'asked':p['asked'],'decision':p['status']}
    for m,ordr in p['orders'].items():
        assert len(ordr)==len(set(ordr))==5
        slots=[full[j] for j in ordr]
        anyhit,allhit,ndcg=evaluate_retrieval(slots,gold,ids,5)
        row[m]=int(allhit);row[m+'_any']=int(anyhit);row[m+'_ndcg']=float(ndcg)
    row['ceiling20']=int(set(gold)<=set(rankids) and len(set(gold))<=5)
    scored.append(row)
assert len(scored)==470
with (outdir/'per_question.csv').open('w',encoding='utf8',newline='') as fp:
    w=csv.DictWriter(fp,fieldnames=list(scored[0]));w.writeheader();w.writerows(scored)
for m in methods:
    v=np.array([r[m]-r['parent'] for r in scored])
    win=int(np.sum(v>0));loss=int(np.sum(v<0)); d=win+loss
    rng=np.random.default_rng(20261116); ci=np.percentile(rng.choice(v,(10000,len(v)),replace=True).mean(axis=1)*100,[2.5,97.5])
    by[m]={'all':sum(r[m] for r in scored),'any':sum(r[m+'_any'] for r in scored),'ndcg':sum(r[m+'_ndcg'] for r in scored)/len(scored),'win':win,'loss':loss,'ties':470-d,'delta_pp':float(100*v.mean()),'interval_pp':ci.tolist(),'p_exact':(min(1.,2*sum(math.comb(d,j) for j in range(min(win,loss)+1))/(2**d)) if d else 1.)}
result={'population':470,'methods':by,'top20_slot_feasible':sum(r['ceiling20'] for r in scored),'top20_all':sum(set(q['answer_session_ids'])<=set(ranked[q['question_id']]['top20_session_ids']) for q in data if not q['question_id'].endswith('_abs')),'disposition_500':dict(collections.Counter(p['status'] for p in preds)),'pred_sha256':hashlib.sha256((outdir/'predictions.jsonl').read_bytes()).hexdigest(),'per_type':{t:{m:sum(r[m] for r in scored if r['type']==t) for m in methods+[]} | {'n':sum(r['type']==t for r in scored)} for t in sorted({r['type'] for r in scored})},'usage':{k:sum(p['usage'].get(k,0) or 0 for p in preds) for k in ('input_tokens','cached_input_tokens','output_tokens')}}
(outdir/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))

