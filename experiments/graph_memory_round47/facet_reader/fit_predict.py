"""Fit on training repositories, then seal every dev/test ranking before scoring."""
from features import *
from sklearn.linear_model import LogisticRegression
import sklearn,time

def train(x,y,c):
    mu=x.mean(0);sd=x.std(0);sd[sd<1e-7]=1.
    beta=[];inter=[]
    for col in y.T:
        prior=(col.sum()+.5)/(len(col)+1)
        if len(set(col))==1:b=np.zeros(x.shape[1]);i=math.log(prior/(1-prior))
        else:
            fit=LogisticRegression(C=c,solver='lbfgs',max_iter=1500,tol=1e-7).fit((x-mu)/sd,col)
            b=fit.coef_[0];i=fit.intercept_[0]
        beta.append(b.tolist());inter.append(float(i))
    return dict(mu=mu.tolist(),sd=sd.tolist(),beta=beta,inter=inter,c=c)
def apply(m,x):
    v=((x-np.asarray(m['mu']))/m['sd'])@np.asarray(m['beta']).T+m['inter']
    return 1/(1+np.exp(-np.clip(v,-50,50)))
def greeds(order,g,mode,seen,lex,union):
    mask=np.asarray(seen,dtype=bool);n=len(order);b=np.empty(n)
    b[order]=1/np.sqrt(np.arange(n)+1)
    init=b+.65*g.sum(1)
    if mode=='dynamic':score=init
    elif mode=='static':score=init
    elif mode=='placebo':score=init
    elif mode=='union':score=b+.65*union
    elif mode=='lex':score=b+.65/np.sqrt(lex)
    else:raise KeyError(mode)
    valid=[j for j in order if not mask[j]];others=[j for j in order if mask[j]]
    if mode in ('static','union','lex'):return sorted(valid,key=lambda i:-score[i])+others
    residual=np.ones(4);keep=np.asarray(valid,int);prefix=[]
    while len(keep):
        gain=b[keep]+.65*(g[keep]@residual);pos=np.argmax(gain);j=int(keep[pos]);prefix.append(j)
        residual*=1-g[j];keep=np.delete(keep,pos)
    return prefix+others
def perturbed(q,g):
    a=g.copy()
    for j,r in enumerate(g):
        key=hashlib.sha256(('R47-placebo/'+q+'/'+str(j)).encode()).digest()
        order=sorted(range(4),key=lambda k:(key[k],k));a[j]=r[order]
    assert np.allclose(a.sum(1),g.sum(1))
    return a
def main():
    started=time.perf_counter();assert sha(D/'PROTOCOL_RU.md')==PROTOCOL
    fp=CACHE/'r47-role-features.json.gz';assert sha(fp)==read(D/'feature-seal.json')['numeric'];data=read(fp)
    splits={s:sorted(q for q,i in data.items() if i['split']==s) for s in ('train','dev','test')}
    rs={s:{data[q]['repo'] for q in h} for s,h in splits.items()}
    assert [len(v) for v in splits.values()]==[179,101,214] and not any(rs[a]&rs[b] for a,b in [('train','dev'),('train','test'),('dev','test')])
    tr=splits['train'];lab=labels(tr);xy=[targets(data[q]['ids'],lab[q]) for q in tr]
    y=np.concatenate([v[0] for v in xy]);yd=np.stack([v[1] for v in xy]);fx=np.concatenate([data[q]['x'] for q in tr]);ux=np.stack([data[q]['u'] for q in tr])
    m=train(fx,np.column_stack((y,y.max(1))),.15);dm=train(ux,yd,.1)
    write('model.json',dict(candidate=m,demand=dm,train_role_support=y.sum(0).tolist(),train_demand_support=yd.sum(0).tolist(),train_rows=len(y),roles=ROLES,sklearn=sklearn.__version__))
    frozen=signed(R46,'forecasts.json.gz');pan=signed(R45,'panel.json')
    pred={};numeric={}
    for q in splits['dev']+splits['test']:
        st=data[q];seen=st['seen'];x=np.asarray(st['x']);u=np.asarray(st['u']);pr=apply(m,x);p=pr[:,:4];union=pr[:,4]/pr[:,4].max();demand=apply(dm,u)
        g=p/np.maximum(1.e-20,p.max(0))*demand;g/=g.sum(1).max()
        rnd=perturbed(q,g);lex=np.asarray(st['lex']);bl=sorted(range(len(lex)),key=lambda j:lex[j])
        orders={'bm':bl};a={'bm':bl,'bm_mask':sorted(bl,key=lambda j:seen[j])}
        if q in frozen:
            fr=frozen[q];assert fr['ids']==st['ids'] and fr['seen']==seen
            for n in ('qwen','dpp','mmr','qwen_mask','dpp_mask','mmr_mask'):a[n]=fr['rank'][n]
            orders['qwen']=a['qwen']
        for name,o in orders.items():
            for s,mask in [('',[0]*len(bl)),('_mask',seen)]:
                for mode in ['dynamic','static','placebo','lex','union']:
                    a[name+'_'+mode+s]=greeds(o,rnd if mode=='placebo' else g,mode,mask,lex,union)
        assert all(sorted(r)==list(range(len(bl))) for r in a.values())
        pred[q]=dict(ids=st['ids'],rank=a,repo=st['repo'],split=st['split'],seen=seen)
        numeric[q]=dict(p=p.tolist(),union=pr[:,4].tolist(),demand=demand.tolist())
    write('predictions.json.gz',pred);write('predicted-roles.json.gz',numeric)
    write('panels.json',dict(train=tr,dev=splits['dev'],test=pan['order'],outside=pan['remaining'],pilot=pan['pilot']))
    write('seal.json',dict(protocol=PROTOCOL,features=sha(D/'feature-seal.json'),model=sha(D/'model.json'),code=sha(Path(__file__)),numbers=sha(D/'predicted-roles.json.gz'),
                           pred=sha(D/'predictions.json.gz'),panels=sha(D/'panels.json'),prior=sha(R46/'manifest.json'),seconds=time.perf_counter()-started,
                           repos={s:len(v) for s,v in rs.items()},states={s:len(v) for s,v in splits.items()}))
    print('Sealed all ranks and out-of-repository role probabilities for',len(pred),'states.')
if __name__=='__main__':main()

