from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json,os,sys
from engine import ROOT,DATA,create
from policy import Actor,visible,kind
ARMS=['none','recent','cursor','full','raw','rate']
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=1))
def replay(row):
    train,game=row; episode=game['episode'];key=hashlib.sha256(episode.encode()).hexdigest()[:20]
    folder=ROOT/('train_logs' if train else 'traces');out=folder/(key+'.json.gz')
    if out.exists():return
    env=create(DATA/episode); logs=[]
    priors={} if train else json.loads((ROOT/'learned.json').read_bytes())
    for arm in (['scout'] if train else ARMS):
        s=env.reset();first=s.feedback;cmds=sorted(s.admissible_commands);actor=Actor(first,cmds,arm,priors)
        steps=[];samples=[];place='';sampled=set()
        if train:
            order=sorted(actor.places,key=lambda p:hashlib.sha256((episode+p).encode()).hexdigest())
        for i in range(50):
            cmds=sorted(s.admissible_commands)
            if train:
                if place and ('open '+place) not in cmds and place not in sampled:
                    samples.append([place,sorted(visible(cmds,place))]);sampled.add(place)
                action='open '+place if place and 'open '+place in cmds else next(('go to '+p for p in order if p not in sampled and 'go to '+p in cmds),None)
                if not action:break
            else:action=actor.act(cmds)
            assert action in cmds
            s,rew,done=env.step(action);actor.update(action,s.feedback)
            steps.append({'available':cmds,'command':action,'feedback':s.feedback,'reward':int(rew),'won':bool(s.won),'done':bool(done),'searched':actor.searched,'retained_search_entries':len(actor.history)+int(actor.cursor is not None)})
            if action.startswith('go to '):place=action[6:]
            if done:break
        logs.append({'episode':episode,'arm':arm,'initial':first,'steps':steps,'samples':samples})
    env.close()
    tmp=out.with_suffix('.tmp')
    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump(logs,f)
    os.replace(tmp,out)
def main():
    train=sys.argv[1]=='train';roster=json.loads((ROOT/'roster.json').read_bytes())
    if not train:
        lock=json.loads((ROOT/'lock.json').read_text());assert all(digest(ROOT/k)==v for k,v in lock.items())
    folder=ROOT/('train_logs' if train else 'traces');folder.mkdir(exist_ok=True)
    with ProcessPoolExecutor(3) as pool:list(pool.map(replay,[(train,g) for g in roster['train' if train else 'valid_unseen']]))
    if train:
        from collections import Counter
        hits=defaultdict(Counter);seen=Counter()
        for path in sorted(folder.glob('*.gz')):
            record=json.loads(gzip.decompress(path.read_bytes()))[0]
            for place,names in record['samples']:
                cls=kind(place);seen[cls]+=1
                for obj in names:hits[obj][cls]+=1
        write_json(ROOT/'learned.json',{'seen':seen,'hits':hits})
        files=['PROTOCOL.md','AMENDMENT-before-eval.md','policy.py','engine.py','roll.py','roster.py','roster.json','learned.json']+[p.relative_to(ROOT).as_posix() for p in sorted(folder.glob('*.gz'))]
        write_json(ROOT/'lock.json',{name:digest(ROOT/name) for name in files})
    print('completed',len(list(folder.glob('*.gz'))))
if __name__=='__main__':main()
