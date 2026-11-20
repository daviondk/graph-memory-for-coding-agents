import collections,os,re,json,gzip,time
os.environ["OPENBLAS_NUM_THREADS"]="2"
import numpy as np
from prepare import read,write,sha,P
from emb import session,batch
from rank import matrices,ARMS
from evaluate import hits,aggregate,contrast
def ingest():
    base=read('input.json');new=read('upstream/lc_locomo10_dialog.json');comp=read('upstream/lc_locomo10_multimem_full.json')
    qs=collections.defaultdict(list);gold={};sty={}
    for bi,(c,v) in enumerate(zip(base,new)):
        assert c['id']==v['sample_id']
        for j,(orig,q) in enumerate(zip(c['queries'],v['qa'])):
            assert q['question']==orig['text']
            if q['category']==5:continue
            for typ in ['dialog','implicit','counterfactual']:
                s=q.get(typ+'_query')
                if isinstance(s,str) and s.strip():
                    k=f"{c['id']}:{typ}:{j}";qs[c['id']].append(dict(id=k,text=s.strip()));gold[k]=q['evidence'];sty[k]=typ
    for j,item in enumerate(comp):
        c=base[item['sample_idx']];s=item.get('composed_query')
        if isinstance(s,str) and s.strip():
            k=f"{c['id']}:composed:{j}";qs[c['id']].append(dict(id=k,text=s.strip()));gold[k]=item['gold_dia_ids'];sty[k]='composed'
    for c in base:c['queries']=qs[c['id']]
    return base,gold,sty
def main():
    data,gold,sty=ingest();qtext=set(q['text'] for c in data for q in c['queries'])
    chars=sorted(qtext,key=lambda s:(len(s),sha(s)));so,tok=session('encoder');base_idx=read('cache/index.json');extra=np.zeros((len(chars),384),dtype='float32')
    for j in range(0,len(chars),32):
        enc=tok.encode_batch(chars[j:j+32]);(H,),mask=batch(so,enc);z=(H*mask[:,:,None]).sum(axis=1)/mask.sum(axis=1)[:,None];extra[j:j+len(enc)]=z/np.maximum(1e-7,np.linalg.norm(z,axis=1,keepdims=True))
    allvec=np.concatenate([np.load(P/'cache/embeddings.npy'),extra]);idx={k:i for i,k in enumerate(base_idx+[sha(s) for s in chars])}
    weights=read("weights.json");preds={}
    for c in data:
        X,ss,_=matrices(c,idx,allvec);k=c['id'];T=c['turns']
        for arm,cols in ARMS.items():
            b=weights[k][arm];ss[arm]=np.einsum('ijk,k->ij',X[:,:,cols],np.array(b[1:],dtype=np.float32))+b[0]
        rank={a:np.argsort(-s,axis=1,kind='stable')[:,:10] for a,s in ss.items()}
        for j,q in enumerate(c['queries']):preds[q['id']]={a:[T[i]['id'] for i in rn[j]] for a,rn in rank.items()}
    out=P/'conversational_predictions.json.gz';out.write_bytes(gzip.compress(json.dumps(preds,separators=(',',':')).encode(),mtime=0))
    write('conversational_lock.json',{"weights_sha":sha((P/'weights.json').read_bytes()),"predictions_sha":sha(out.read_bytes()),"script":sha((P/'conversational.py').read_bytes()),"protocol":sha((P/'CONVERSATIONAL_TRANSFER.md').read_bytes()),"inputs":{s:sha((P/'upstream'/s).read_bytes()) for s in ('lc_locomo10_dialog.json','lc_locomo10_multimem_full.json')}})
def score():
    data,gold,sty=ingest();out=P/'conversational_predictions.json.gz';assert sha(out.read_bytes())==read('conversational_lock.json')['predictions_sha']
    ps=json.loads(gzip.decompress(out.read_bytes()));pool={c['id']:{t['id'] for t in c['turns']} for c in data};by=collections.defaultdict(dict)
    for i,pred in ps.items():
        g=set(gold[i]);conv=i.split(':')[0]
        if not g or not g<=pool[conv]:continue
        by[sty[i]][i]={a:{**hits(r,g,5),**hits(r,g,10)} for a,r in pred.items()}
    total={}
    for s,rows in by.items():total[s]={"n":len(rows),"means":aggregate(rows),"graph_minus_flat":{m:contrast(rows,'flat',m) for m in ("all@5","recall@10")}}
    write("conversational_results.json",total)
if __name__=='__main__':main();score()