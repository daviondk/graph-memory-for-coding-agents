"""All scorers receive only the pre-failure projection and strictly completed memory receipts."""
import hashlib
from collections import defaultdict,deque
class Bank:
    def __init__(self):
        self.sums=defaultdict(lambda:[0,0]);self.short=defaultdict(lambda:deque(maxlen=32))
    def keys(self,r):
        repo=r['repo'];s=r['status'];detail=(s,r['event'],r['language'],r['matrix'])
        sig=tuple(r.get('reasons',[]))
        return {'all':('all',),'status':('s',s),'project':('p',repo),'ps':('ps',repo,s),
                'context':('ctx',detail),'pc':('pc',repo,detail),'type':('t',s,sig),'pt':('pt',repo,s,sig)}
    def add(self,r,y):
        for k in self.keys(r).values():
            self.sums[k][0]+=y;self.sums[k][1]+=1;self.short[k].append(y)
    def scores(self,r):
        k=self.keys(r)
        def sm(name,prior,count=8,limit=0):
            if limit:
                h=list(self.short[k[name]])[-limit:];n=len(h);s=sum(h)
            else:s,n=self.sums[k[name]]
            return (s+count*prior)/(n+count)
        g=sm('all',.5,2);s=sm('status',g);pro=sm('project',g);ps=sm('ps',s);ctx=sm('context',s)
        v={'random':.5,'last_status':0.,'global':g,'status':s,'repo':pro,'repo_status':ps,'global_context':ctx,
           'last_repo':float(self.short[k['project']][-1]) if self.short[k['project']] else g,
           'recent8':sm('pc',ctx,limit=8),'recent1':sm('pc',ctx,limit=1),'recent32':sm('pc',ctx,limit=32),
           'context_all':sm('pc',ctx),'matching':len(self.short[k['pc']])}
        if 'reasons' in r:
            gt=sm('type',s);exact=len(self.short[k['pt']])
            typed=sm('pt',gt,limit=8) if r['reasons'] else ps
            v.update(typed=typed,global_type=gt,typed_if_uncertain=typed if .35<=ps<=.65 else ps,
                     typed_if_sparse=typed if self.sums[k['ps']][1]<8 else ps,typed_matching=exact,
                     uncertain=int(.35<=ps<=.65),sparse=int(self.sums[k['ps']][1]<8))
        return v
def stable(i,salt='retry-priority'):
    return hashlib.sha256((salt+'|'+str(i)).encode()).hexdigest()
