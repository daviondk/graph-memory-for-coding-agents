from run import *

def main():
    assert load(D/'decision_lock.json')['predictions']==sha(D/'decisions.jsonl.gz')
    save('ablation_lock.json',dict(utc=now(),method=sha(D/'ABLATION_RU.md'),source=sha(D/'ablate.py'),
         original=sha(D/'method_lock.json')))
    plan=load(D/'roster.json')
    tasks=lambda train:[(p,k,ids) for p,v in plan.items() for k,ids in v.items() if bool(k=='train')==train and ids]
    train,x,y,w=transform(tasks(True))
    cols={'r4_shape':list(range(52)),'r4_alignment':list(range(43))+list(range(52,x.shape[1]-32))}
    models={}
    for arm,ids in cols.items():
        m=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,min_samples_leaf=28,
            learning_rate=.10,l2_regularization=1,random_state=261119,early_stopping=False)
        models[arm]=m.fit(x[:,ids],y,sample_weight=w)
    with (D/'ablation_models.pkl').open('wb') as f:pickle.dump(models,f)
    save('ablation_fit_lock.json',dict(utc=now(),weights=sha(D/'ablation_models.pkl'),cols=cols))
    cases,allx,_,_=transform(tasks(False));out=[];off=0
    scores={a:m.predict_proba(allx[:,cols[a]])[:,1] for a,m in models.items()}
    for stage,panel,i,repo,n,h,q,_ in cases:
        orders={a:np.argsort(-s[off:off+n],kind='stable').tolist() for a,s in scores.items()}
        out.append([stage,panel,i,repo,n,h,q,orders]);off+=n
    writegz('ablation_decisions.jsonl.gz',out)
    save('ablation_decision_lock.json',dict(utc=now(),weights=sha(D/'ablation_models.pkl'),
         decisions=sha(D/'ablation_decisions.jsonl.gz'),n=len(out)))
if __name__=='__main__':main()
