import gzip,json,tempfile,sys,os
from pathlib import Path
import numpy as np
from prepare import P,read,write,sha
from rank import ARMS,matrices
from emb import session,batch
from conversational import ingest
from importlib.util import spec_from_file_location,module_from_spec
def main():
    data,gold,sty=ingest();author=read('upstream/lc_locomo10_dialog.json');comp=read('upstream/lc_locomo10_multimem_full.json')
    for c,v in zip(data,author):
        c['queries']=[]
        for j,qa in enumerate(v['qa']):
            if qa['category']!=5:continue
            for typ in ('dialog','implicit'):
                txt=qa.get(typ+'_query')
                if isinstance(txt,str) and txt.strip():
                    c['queries'].append(dict(id=f"{c['id']}:{typ}:{j}",text=txt.strip()))
    texts=sorted({q['text'] for c in data for q in c['queries']},key=lambda s:(len(s),sha(s)));so,tok=session('encoder')
    vextra=[]
    for j in range(0,len(texts),32):
        enc=tok.encode_batch(texts[j:j+32]);(H,),m=batch(so,enc);z=(H*m[:,:,None]).sum(axis=1)/m.sum(axis=1)[:,None];vextra.append((z/np.maximum(1e-7,np.linalg.norm(z,axis=1,keepdims=True))).astype('float32'))
    vec=np.concatenate([np.load(P/'cache/embeddings.npy'),*vextra]);idx={v:i for i,v in enumerate(read('cache/index.json')+[sha(t) for t in texts])}
    weights=read("weights.json");pred=json.loads(gzip.decompress((P/'conversational_predictions.json.gz').read_bytes()));new={}
    for c in data:
        X,_,_=matrices(c,idx,vec);k=c['id']
        for a in ('flat','graph'):
            w=weights[k][a];s=np.einsum('ijk,k->ij',X[:,:,ARMS[a]],np.array(w[1:],dtype=np.float32))+w[0];rank=np.argsort(-s,axis=1,kind='stable')[:,:10]
            for j,q in enumerate(c['queries']):new.setdefault(q['id'],{})[a]=[c['turns'][i]['id'] for i in rank[j]]
    included=len(new);assert not set(pred)&set(new);pred.update(new)
    (P/'official_extra_predictions.json.gz').write_bytes(gzip.compress(json.dumps(new,separators=(',',':')).encode(),mtime=0))
    logs={}
    scorer=P/'upstream/lc_compute_retrieval_metrics.py'
    spec=spec_from_file_location("upstream_official_scorer",scorer);mod=module_from_spec(spec);spec.loader.exec_module(mod)
    old=sys.argv[:]
    for a in ('flat','graph'):
        with tempfile.TemporaryDirectory(dir=P/"cache") as tmp:
            for ci,c in enumerate(author):
                path=Path(tmp)/f"sample_{ci}";path.mkdir();srct={t['dia_id']:t['text'] for f,L in c['conversation'].items() if isinstance(L,list) for t in L};k=c['sample_id']
                def record(key):
                    ids=pred[key][a]
                    return dict(docs=[srct[j] for j in ids],retrieved_metadata=[{'dia_ids':j} for j in ids])
                for typ in ('dialog','implicit','counterfactual'):
                    field=typ+'_query';ordered=mod.select_qas_in_main_order(c['qa'],field)
                    obj=[record(f"{k}:{typ}:{j}") for j,_ in ordered]
                    (path/f"queries_solutions_{field}.json").write_text(json.dumps(obj),encoding='utf8')
                obj=[]
                for j,rec in enumerate(comp):
                    if rec['sample_idx']==ci and rec.get('composed_query'):
                        obj.append({**record(f"{k}:composed:{j}"),'cluster_id':rec['cluster_id'],'gold_dia_ids':rec['gold_dia_ids']})
                (path/'composed_solutions.json').write_text(json.dumps(obj),encoding='utf8')
            out=Path(tmp)/"metrics.json";sys.argv=[str(scorer),'--dataset_path',str(P/'upstream/lc_locomo10_dialog.json'),'--multimem_path',str(P/'upstream/lc_locomo10_multimem_full.json'),'--results_dir',tmp,'--styles','dialog,implicit,counterfactual,composed','--out',str(out)]
            mod.main();logs[a]=json.loads(out.read_bytes())
    sys.argv=old;write('official_conv_results.json',dict(extra_query_count=included,source_hash=sha(scorer.read_bytes()),protocol_hash=sha((P/'CONV_OFFICIAL.md').read_bytes()),results=logs))
if __name__=='__main__':main()