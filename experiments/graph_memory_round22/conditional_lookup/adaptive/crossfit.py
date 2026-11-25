"""Out-of-fold forecasts. The only labelled input to a fold is its own training file."""
import os
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[k]="1"
from collections import Counter
import sys
from pathlib import Path
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from freeze import D, read, dump, digest


def predict_probability(x,y,weights,targets):
    keep=weights>0
    x,y,weights=x[keep],y[keep],weights[keep]
    if len(np.unique(y))<2:
        probability=(float(weights@y)+0.5)/(weights.sum()+1.)
        return np.full(len(targets),probability),dict(constant=probability)
    model=LogisticRegression(C=0.25,solver='liblinear',fit_intercept=True,intercept_scaling=1,
                             tol=1e-9,max_iter=500,random_state=2220)
    model.fit(x,y,sample_weight=weights)
    assert model.n_iter_[0]<500
    return model.predict_proba(targets)[:,1],dict(w=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),iterations=int(model.n_iter_[0]))


def one_fold(fold):
    locks=read(D/'training-lock.json');features=read(D/'feature-lock.json')
    assert digest(D/'feature-lock.json')==locks['feature_lock'] and digest(D/'features.json.gz')==features['inputs']
    rows=read(D/'features.json.gz');by_id={r['id']:r for r in rows}
    file=D/f'train-excluding-{fold}.json.gz'
    assert digest(file)==locks['files'][file.name]
    labels=read(file);ts=[r for r in rows if r['fold']==fold]
    trainrows=[by_id[z['id']] for z in labels]
    assert all(r['fold']!=fold for r in trainrows)
    assert not ({r['comp'] for r in trainrows}&{r['comp'] for r in ts})
    x=np.array([r['x'] for r in trainrows]);y=np.array([z['y'] for z in labels]);xt=np.array([r['x'] for r in ts])
    probability,model=predict_probability(x,y,np.ones(len(y)),xt)
    choices=[]
    for r,p in zip(ts,probability,strict=True):
        arm='neighbor' if p>=.5 else 'hybrid'
        choices.append(dict(id=r['id'],fold=fold,p_neighbor_if_discordant=float(p),choice=arm,addresses=r['picks'][arm]))
    dest=D/f'forecast-{fold}.json.gz'
    dump(dest,choices)
    dump(D/f'model-{fold}.json',dict(fold=fold,model=model,labels=digest(file),n_train=len(y),n_neighbor_wins=int(y.sum()),
         train_components=len({r['comp'] for r in trainrows}),n_forecast=len(ts),test_components=len({r['comp'] for r in ts}),
         forecast=digest(dest),code=digest(Path(__file__)),numpy=np.__version__,sklearn=sklearn.__version__))


def seal():
    allrows={};model={}
    for k in range(5):
        z=read(D/f'model-{k}.json');path=D/f'forecast-{k}.json.gz'
        assert z['forecast']==digest(path) and z['code']==digest(Path(__file__))
        f=read(path);assert not set(allrows)&{r['id'] for r in f};allrows.update({r['id']:r for r in f});model[str(k)]=digest(D/f'model-{k}.json')
    assert set(allrows)=={r['id'] for r in read(D/'features.json.gz')}
    dump(D/'forecast-lock.json',dict(training=digest(D/'training-lock.json'),code=digest(Path(__file__)),models=model,
         n=len(allrows),choices=Counter(r['choice'] for r in allrows.values())))


if __name__=='__main__':
    if sys.argv[1]=='seal':seal()
    else:one_fold(int(sys.argv[1]))

