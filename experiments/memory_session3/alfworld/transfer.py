"""Independent frozen experiment varying conditional reads and online negative feedback."""
import collections,csv,gzip,hashlib,json,os,sys,zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from policy import Actor,kind,order
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[3];DATA=BASE/'x20-session3-alfgames'/'json_2.1.1'
ARMS=['all_static','room_static','all_miss','room_miss']
def read(p):return json.loads((ROOT/p).read_bytes())
def save(p,x):(ROOT/p).write_text(json.dumps(x,indent=1,sort_keys=True))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    from roster import KINDS
    roster=[];mem=[]
    with zipfile.ZipFile(BASE/'x20-session3-alfmeta.zip') as meta:
        for g in sorted((DATA/'valid_seen').glob('*/*/game.tw-pddl')):
            path=g.relative_to(DATA).as_posix()
            if 'movable' in path or 'Sliced' in path:continue
            try:m=json.loads(meta.read('json_2.1.1/'+path.replace('game.tw-pddl','traj_data.json')))
            except KeyError:continue
            if m['task_type'] in KINDS and json.loads(g.read_bytes()).get('solvable'):
                roster.append({'episode':path,'family':m['task_type'],'floorplan':str(m['scene']['scene_num']),'game_sha':sha(g)})
    for fn in sorted((ROOT/'train_logs').glob('*.gz')):
        r=json.loads(gzip.decompress(fn.read_bytes()))[0];s=r['steps'][0]
        mem.append({'room':sorted({kind(c[6:]) for c in s['available'] if c.startswith('go to ')}),'samples':r['samples'],'episode':r['episode']})
    save('transfer_seen.json',roster);save('training_rooms.json',mem)
    frozen=['TRANSFER_PROTOCOL.md','transfer.py','transfer_score.py','transfer_seen.json','training_rooms.json','policy.py','engine.py','lock.json']
    save('transfer_lock.json',{f:sha(ROOT/f) for f in frozen});print('registered',len(roster),'seen episodes',len(mem),'training logs')
class ConditionalActor(Actor):
    def search(self,target,commands):
        if 'open '+self.place in commands:return 'open '+self.place
        self.remember(self.place)
        if target not in self.ranks:
            hits=collections.Counter();trials=collections.Counter();allhits=0;allcnt=0
            room={kind(p) for p in self.places}
            for record in self.records:
                r=set(record['room']);w=(len(r&room)/len(r|room))**4 if self.arm.startswith('room') else 1
                for place,objs in record['samples']:
                    cl=kind(place);present=int(target in objs);hits[cl]+=w*present;trials[cl]+=w
                    allcnt+=1;allhits+=present
            p0=(allhits+1)/(allcnt+2)
            self.ranks[target]={cl:(hits[cl]+4*p0)/(trials[cl]+4) for cl in room}
        miss=collections.Counter(kind(p) for p in self.history)
        def score(p):
            cl=kind(p);rate=self.ranks[target][cl]
            if self.arm.endswith('miss'):rate*=4/(4+miss[cl])
            return -rate,order(p)
        pool=sorted(self.places,key=score)
        return self.travel([p for p in pool if p not in self.history]+[p for p in pool if p in self.history],commands) or 'look'
def roll(game):
    from engine import create
    ep=game['episode'];out=ROOT/'transfer_traces'/(hashlib.sha256(ep.encode()).hexdigest()[:20]+'.json.gz')
    if out.exists():return
    env=create(DATA/ep);rows=[]
    for arm in (ARMS if ep.startswith('valid_unseen') else ARMS+['full','rate']):
        s=env.reset();first=s.feedback
        actor=(ConditionalActor if arm in ARMS else Actor)(first,sorted(s.admissible_commands),arm,read('learned.json'))
        actor.ranks={};actor.records=read('training_rooms.json');steps=[]
        for i in range(50):
            cmds=sorted(s.admissible_commands);cmd=actor.act(cmds);assert cmd in cmds
            s,reward,done=env.step(cmd);actor.update(cmd,s.feedback)
            steps.append({'command':cmd,'available':cmds,'feedback':s.feedback,'won':bool(s.won),'done':bool(done),'reward':int(reward),'searched':actor.searched})
            if done:break
        rows.append({'episode':ep,'arm':arm,'initial':first,'steps':steps})
    env.close();tmp=out.with_suffix('.tmp')
    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump(rows,f)
    os.replace(tmp,out)
if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    else:
        assert all(sha(ROOT/k)==v for k,v in read('transfer_lock.json').items())
        games=read('roster.json')['valid_unseen']+read('transfer_seen.json')
        games.sort(key=lambda r:hashlib.sha256(('transfer'+r['episode']).encode()).hexdigest())
        (ROOT/'transfer_traces').mkdir(exist_ok=True)
        with ProcessPoolExecutor(3) as pool:list(pool.map(roll,games))
        print('complete',len(games))

