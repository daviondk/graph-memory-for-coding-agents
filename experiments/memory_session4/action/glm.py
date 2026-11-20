from pathlib import Path
import json,math,heapq
from collections import defaultdict
from model import stable
from run import P,load,readgz,writegz
from evaluate import boot
class FTRL:
    """Online FTRL-Proximal logistic regression. No external libraries or pretrained weights."""
    def __init__(self,typed):
        self.z=defaultdict(float);self.n=defaultdict(float);self.typed=typed
    def features(self,r):
        p,s,e,l,m=r['repo'],r['status'],r['event'],r['language'],r['matrix']
        f=[('bias',),('repo',p),('s',s),('e',e),('l',l),('m',m),('ps',p,s),('context',s,e,l,m),('pc',p,s,e,l,m)]
        if self.typed:
            sig=tuple(r['reasons'])
            f.extend([('reason',s,sig),('pr',p,s,sig)])
        return f
    def weighted(self,r):
        f=self.features(r)
        w=[-self.z[k]/((1+math.sqrt(self.n[k]))/.25+1.) for k in f]
        total=max(-35.,min(35.,sum(w)))
        return f,w,1/(1+math.exp(-total))
    def p(self,r):return self.weighted(r)[2]
    def update(self,r,y):
        f,w,p=self.weighted(r);g=p-y
        for k,wi in zip(f,w):
            n=self.n[k];sigma=(math.sqrt(n+g*g)-math.sqrt(n))/.25
            self.z[k]+=g-sigma*wi;self.n[k]+=g*g
def run_glm(kind):
    sources,Y=load(kind);N=len(sources)//2;data={r['id']:r for r in sources}
    ps={r['id']:r['p'] for r in readgz(P/(kind+'_predictions.jsonl.gz'))}
    choices={r['id']:r['accepted'] for r in readgz(P/(kind+'_allocation.jsonl.gz'))}
    def update(b,q,t):
        while q and q[0][0]<t:
            _,i=heapq.heappop(q);b.update(data[i],Y[i]['passed'])
    def enqueue(q,i):heapq.heappush(q,(Y[i]['available_after'],i))
    methods=['glm']+(['glm_type'] if kind=='jobs' else []);records={}
    for arm in methods:
        typed=arm=='glm_type';b=FTRL(typed);q=[]
        for j,r in enumerate(sources):
            i=r['id'];update(b,q,r['decision_at'])
            if j>=N:ps[i][arm]=b.p(r)
            enqueue(q,i)
        b=FTRL(typed);q=[]
        for r in sources[:N]:enqueue(q,r['id'])
        for j in range(N,len(sources),100):
            group=sources[j:j+100];update(b,q,group[0]['decision_at']);m=max(1,int(len(group)*.2+.5))
            for r in sorted(group,key=lambda x:(-b.p(x),stable(x['id'])))[:m]:
                choices[r['id']].append(arm);enqueue(q,r['id'])
    writegz(P/(kind+'_glm_receipts.jsonl.gz'),[{'id':i,'p':{a:ps[i][a] for a in methods},'selected':[a for a in methods if a in choices[i]]} for i in ps])
    arms={}
    pairs=[('glm','repo_status'),('recent8','glm')]
    if kind=='jobs':pairs+= [('glm_type','glm'),('typed','glm_type')]
    for a in methods:
        ids=list(ps);hit=[i for i in ids if a in choices[i]]
        arms[a]={'brier':sum((ps[i][a]-Y[i]['passed'])**2 for i in ids)/len(ids),'selected':len(hit),'recovered':sum(Y[i]['passed'] for i in hit),'hours':sum(Y[i]['duration_s'] for i in hit)/3600}
    for a,b in pairs:
        bl=defaultdict(lambda:[0,0]);gain=defaultdict(lambda:[0,0])
        for i,p in ps.items():
            y=Y[i]['passed'];rp=data[i]['repo']
            bl[rp][0]+=(p[a]-y)**2-(p[b]-y)**2;bl[rp][1]+=1
            gain[rp][0]+=(int(a in choices[i])-int(b in choices[i]))*y;gain[rp][1]+=1
        arms[a+' vs '+b]={'brier':boot(bl),'rescues_per_opportunity':boot(gain)}
    return arms
if __name__=='__main__':
    result={k:run_glm(k) for k in ('builds','jobs')};(P/'glm_results.json').write_text(json.dumps(result,indent=2,sort_keys=True));print('GLM complete')
