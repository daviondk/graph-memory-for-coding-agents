"""Prefix stopping using no future evidence and no target labels."""
from collections import Counter,defaultdict
import json
from transformers import AutoTokenizer
from source import ROOT,R8,CACHE,load_json,write_json,h,member,base
def run(t,tokenizer):
    p=load_json(ROOT/'predictions'/(t+'.json'))
    dense=p['ranks']['dense']; pos={s:i+1 for i,s in enumerate(dense)}
    outsiders=set(dense[10:])
    ids={s for s in outsiders if s.split('/')[-1] in p['query_identifiers']}
    raw=[json.loads(b) for b in member(base(t)+'corpus.jsonl').splitlines()]
    docs={r['_id']:r['text'] for r in raw}
    seed_cost={s:{'bytes':len(docs[s].encode('utf8')),'tokens':len(tokenizer(docs[s],add_special_tokens=False,truncation=False,verbose=False)['input_ids'])} for s in p['seed']}
    # The simulator exposes edges by their recorded source — each action opens the next source gate.
    rows=defaultdict(set)
    for src,_,dst in p['stored_edges']:rows[src].add(dst)
    result={}
    for method in ['fixed6','early','early3']:
        support=Counter();picked=None;trace=[]
        for src in p['seed']:
            revealed=rows[src]&outsiders
            support.update(revealed)
            chosen=sorted((s for s in support if support[s]+int(s in ids)>=2),key=lambda s:(-(support[s]+int(s in ids)),pos[s]))
            trace.append({'source':src,'outside_edges':sorted(revealed),'eligible':chosen[:1]})
            if chosen and (method!='fixed6' or len(trace)==6):
                picked=chosen[0];break
            if method=='early3' and len(trace)==3 and not support and not ids:break
        new=dense[:9]+[picked]+[s for s in dense[9:] if s!=picked] if picked else dense.copy()
        result[method]={'reads':len(trace),'tokens':sum(seed_cost[r['source']]['tokens'] for r in trace),'bytes':sum(seed_cost[r['source']]['bytes'] for r in trace),'fresh':picked,'base_position':pos[picked] if picked else None,'trace':trace,'rank':new}
    wanted=p['suggestions']['corroborated'][:1]
    assert result['fixed6']['fresh']==(wanted[0] if wanted else None)
    return {'issue':t,'policies':result}
def main():
    out=ROOT/'stop_predictions';out.mkdir(exist_ok=True)
    tok=AutoTokenizer.from_pretrained(str(CACHE/'model'),local_files_only=True)
    sample=load_json(ROOT/'sample.json')['selected']
    for r in sample:
        t=r['issue'];dest=out/(t+'.json')
        if (ROOT/'predictions'/(t+'.json')).exists() and not dest.exists():write_json(dest,run(t,tok))
    if len(list(out.glob('*.json')))==len(sample) and (ROOT/'blind_seal.json').exists():
        paths=[ROOT/'STOPPING_PROTOCOL.md',ROOT/'stop_predict.py',ROOT/'stop_score.py',ROOT/'blind_seal.json']+list(out.glob('*.json'))
        write_json(ROOT/'stop_seal.json',{p.relative_to(ROOT).as_posix():h(p.read_bytes()) for p in paths})
if __name__=='__main__':main()
