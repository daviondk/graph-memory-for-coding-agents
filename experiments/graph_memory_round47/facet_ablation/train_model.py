from pathlib import Path
import sys,hashlib,json,gzip
import numpy as np
D=Path(__file__).resolve().parent;BASE=D.parent/'facet_reader';CONF=D.parent/'facet_confirmation'
sys.path.insert(0,str(BASE))
from fit_predict import train,apply
from features import read,sha,labels,targets,CACHE
def dump(name,val):
    b=(json.dumps(val,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if name.endswith('.gz') else b)
def main():
    assert sha(D/'PROTOCOL_RU.md')=='ffa63bf6c98b2a69cc8c0988e4e3a3009c82de94306b24873ae02e033138852d'
    assert sha(BASE/'manifest.json')=='bc49b664345dcb30c91ef75378d19d995c0361e8c66ff6bb920322688418ad5d'
    sig=read(BASE/'manifest.json')['files']
    for k in ['panels.json','feature-seal.json','model.json','predicted-roles.json.gz','fit_predict.py','features.py']:assert sha(BASE/k)==sig[k]
    p=read(BASE/'panels.json');old=read(BASE/'predicted-roles.json.gz');fc=CACHE/'r47-role-features.json.gz';assert sha(fc)==read(BASE/'feature-seal.json')['numeric']
    data=read(fc);train_q=p['train'];truth=labels(train_q)
    x=np.concatenate([data[q]['x'] for q in train_q]);y=np.concatenate([targets(data[q]['ids'],truth[q])[0].max(1) for q in train_q])[:,None]
    schemas={'document':list(range(20)),'match':list(range(20,70))+list(range(82,109))}
    models={k:train(x[:,cols],y,.15) for k,cols in schemas.items()}
    full=train(x,y,.15);prior=read(BASE/'model.json')['candidate']
    assert np.max(abs(np.array(full['beta'][0])-np.array(prior['beta'][-1])))==0.
    assert float(full['inter'][0])==prior['inter'][-1]
    old_diff=[];probs={}
    for q in p['dev']+p['test']:
        xx=np.asarray(data[q]['x']);a={k:apply(models[k],xx[:,cols])[:,0].tolist() for k,cols in schemas.items()};pp=apply(full,xx)[:,0];o=np.asarray(old[q]['union']);old_diff.append(np.max(abs(pp-o)))
        assert np.allclose(pp,o,rtol=0,atol=1e-13);a['full']=o.tolist();probs[q]=a
    dump('probabilities.json.gz',probs);dump('models.json',dict(schema=schemas,models=models,train_candidates=len(y),positive=int(y.sum()),max_full_delta=float(max(old_diff))))
    dump('learning-seal.json',dict(prior=sha(BASE/'manifest.json'),protocol=sha(D/'PROTOCOL_RU.md'),prob=sha(D/'probabilities.json.gz'),model=sha(D/'models.json'),code=sha(Path(__file__)),
              dev=len(p['dev']),test=len(p['test']),train=len(train_q)))
    print('Sealed probabilities for',len(probs),'states. Recovered original full model to',max(old_diff))
if __name__=='__main__':main()

