"""Two fixed follow-up fits distinguish graph neighborhoods from the opened-path flag."""
from study import D, read, put, sha, teach, fold, fit, select, retention, summarize, LOCAL, GRAPH, N_LOCAL
import numpy as np
PLAN='0d8089ccfa67ea91e16740a79f7431b72d8c72a7e797c4013c095896e9126ee9'
COLUMNS={'open':list(range(N_LOCAL+1)),'neighbors':list(range(N_LOCAL))+list(range(N_LOCAL+1,N_LOCAL+len(GRAPH)))}

def main():
    assert sha(D/'ABLATION_RU.md')==PLAN
    rows=read(D/'inputs.json.gz');obs=read(D/'outcomes.json.gz');ex=teach(rows);bank={}
    for tag in ['transfer','0','1','2','3','4']:
        bank[tag]={}
        keep=ex if tag=='transfer' else [v for v in ex if str(fold(v[0]))!=tag]
        for m,cols in COLUMNS.items():
            data=[(r,q,X[:,cols],y) for r,q,X,y in keep]
            model=fit(data,'graph');beta=np.zeros(N_LOCAL+len(GRAPH));beta[cols]=model['coef']
            model['coef']=beta.tolist();model['features']=[(LOCAL+GRAPH)[i] for i in cols]
            bank[tag][m]=model
    put('ablation-models.json',bank);result={}
    for q,r in rows.items():
        z=obs[q];out={'local':z['arms']['local'],'graph':z['arms']['graph']}
        for m in COLUMNS:
            coeff=bank[z['fold']][m];assert z['repo'] not in coeff['train_repos'];cur={}
            for s,p in enumerate(r['prev']):
                cur=select(cur,rows[p],s,coeff,True)
            out[m]=retention(cur,r)
        result[q]=out
    put('ablation-outcomes.json.gz',result)
    store={}
    for panel in ['R48','R49']:
        seq=[q for q,z in rows.items() if z['panel']==panel]
        groups={r:[q for q in seq if rows[q]['repo']==r] for r in sorted({rows[q]['repo'] for q in seq})}
        n=len(groups);bs=np.random.default_rng(501271).multinomial(n,np.full(n,1/n),size=20000)
        den=np.array([sum(rows[q]['total'] for q in v) for v in groups.values()])
        vec={m:np.array([sum(result[q][m][1] for q in v) for v in groups.values()]) for m in ['local','open','neighbors','graph']}
        cs={}
        for a,b in [('graph','open'),('graph','neighbors'),('open','local'),('neighbors','local')]:
            dif=vec[a]-vec[b];cs[a+'-'+b]=dict(delta=dif.sum()/den.sum(),tokens=int(dif.sum()),ci=np.quantile((bs@dif)/(bs@den),[.025,.975]).tolist())
        store[panel]=cs
    put('ablation-results.json',dict(protocol=PLAN,panels=store))
    print(store)


if __name__=='__main__':main()

