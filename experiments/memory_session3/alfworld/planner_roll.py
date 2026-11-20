"""Closed-loop replay with the four frozen plan interventions; no LLM observes rewards."""
from roll import replay,write_json,digest
from engine import *
from policy import Actor,kind,order
import gzip,hashlib,os
from concurrent.futures import ProcessPoolExecutor
ARMS=['q_prior','q_shown','q_placebo','q_fused']
def enc(x):return json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':'))
class PlannedActor(Actor):
    def search(self,target,commands):
        if 'open '+self.place in commands:return 'open '+self.place
        self.remember(self.place)
        classes=sorted({kind(p) for p in self.places})
        key=enc([target,classes,'q_prior' if self.arm=='q_fused' else self.arm])
        rank=self.plans.get(key,{'rank':classes})['rank']
        def priority(p):
            c,num=p.rsplit(' ',1);i=rank.index(c)
            if self.arm=='q_fused':
                hits=self.priors['hits'].get(target,{}).get(c,0);seen=self.priors['seen'].get(c,0)
                return int(num),-(hits+8/(i+1))/(seen+8),i
            return int(num),i,c
        pool=sorted(self.places,key=priority)
        return self.travel([p for p in pool if p not in self.history]+[p for p in pool if p in self.history],commands) or 'look'
def run(game):
    ep=game['episode'];out=ROOT/'planner_traces'/(hashlib.sha256(ep.encode()).hexdigest()[:20]+'.json.gz')
    if out.is_file():return
    env=create(DATA/ep);rows=[];plans=json.loads((ROOT/'plans.json').read_bytes());m=json.loads((ROOT/'learned.json').read_bytes())
    for arm in ARMS:
        s=env.reset();first=s.feedback;a=PlannedActor(first,sorted(s.admissible_commands),arm,m);a.plans=plans;steps=[]
        for i in range(50):
            cmds=sorted(s.admissible_commands);action=a.act(cmds);assert action in cmds
            s,reward,done=env.step(action);a.update(action,s.feedback)
            steps.append({'available':cmds,'command':action,'feedback':s.feedback,'reward':int(reward),'won':bool(s.won),'done':bool(done),'searched':a.searched,'retained_search_entries':len(a.history)})
            if done:break
        rows.append({'arm':arm,'episode':ep,'initial':first,'steps':steps})
    env.close();tmp=out.with_suffix('.tmp')
    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump(rows,f)
    os.replace(tmp,out)
if __name__=='__main__':
    for n in ('lock.json','planner_input_lock.json','planner_lock.json'):
        assert all(digest(ROOT/k)==v for k,v in json.loads((ROOT/n).read_bytes()).items())
    roster=json.loads((ROOT/'roster.json').read_bytes())['valid_unseen'];(ROOT/'planner_traces').mkdir(exist_ok=True)
    with ProcessPoolExecutor(3) as ex:list(ex.map(run,roster))
    print('complete',len(roster))

