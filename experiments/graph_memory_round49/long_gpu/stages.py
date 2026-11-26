from panel import *
import numpy as np
def main():
    p=read(D/'panel.json');raw=read(D/'raw-runs.json.gz');r=read(D/'results.json');pieces={}
    repos=[x['repo'] for x in p['selected']];n=len(repos);b=np.random.default_rng(490731).multinomial(n,np.repeat(1/n,n),size=20000)
    for i in range(3):
        sums={};cc={}
        for arm in ('fresh','proposed','lru','gdsf'):
            sums[arm]={k:sum(raw[repo][arm][i][k] for repo in repos) for k in ('tokens','wall_rank','compute_engine_s','calls')}
        for arm in ('lru','gdsf'):
            vals={}
            for k in ('tokens','wall_rank','compute_engine_s'):
                x=np.asarray([raw[repo]['proposed'][i][k] for repo in repos]);y=np.asarray([raw[repo][arm][i][k] for repo in repos])
                vals[k]=dict(saving=float(1-x.sum()/y.sum()),ci=np.quantile(1-(b@x)/(b@y),[.025,.975]).tolist(),wins=int((x<y).sum()),loss=int((x>y).sum()))
            cc[arm]=vals
        pieces[str(i+1)]=dict(sums=sums,contrast=cc)
    put('stage-results.json',dict(source=sha(D/'run-seal.json'),plan=sha(D/'STAGES_RU.md'),program=sha(Path(__file__)),stages=pieces))
if __name__=='__main__':main()

