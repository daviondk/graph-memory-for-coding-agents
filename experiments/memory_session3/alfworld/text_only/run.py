"""Feedback-only ALFWorld evaluator. Score outside actor, two CPU workers."""
import collections,concurrent.futures,gzip,hashlib,json,os,sys,time
from pathlib import Path
from actor import Actor,Scout,kind
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from engine import DATA,AlfredDemangler,textworld
ARMS=['none','pose_cycle','cursor','full','trained']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(p,data):p.write_text(json.dumps(data,sort_keys=True,indent=1),encoding='utf8')
def zipread(p):return json.loads(gzip.decompress(p.read_bytes()))
def episode(input):
    mode,g=input;split='train' if mode=='train' else 'dev' if mode=='dev' else 'eval'
    out=ROOT/split/(hashlib.sha256(g['episode'].encode()).hexdigest()[:20]+'.json.gz')
    if out.exists():return
    priors={} if mode=='train' else read(ROOT/'learned.json')
    game=DATA/g['episode'];assert sha(game)==g['game_sha']
    env=textworld.start(str(game),textworld.EnvInfos(won=True),wrappers=[AlfredDemangler])
    records=[]
    try:
        for arm in (['scout'] if mode=='train' else ARMS):
            state=env.reset();first=state.feedback;actor=Scout(first) if arm=='scout' else Actor(first,arm,priors)
            steps=[]
            for _ in range(50):
                action=actor.action()
                if action is None:break
                state,reward,done=env.step(action)
                feedback=state.feedback; recognized=actor.update(action,feedback)
                retained=0 if arm=='scout' else len(actor.history)+int(actor.cursor is not None)
                steps.append([action,feedback,bool(state.won),bool(done),recognized,retained])
                if done:break
            records.append({'arm':arm,'initial':first,'steps':steps,
                            'samples':actor.samples if arm=='scout' else {}})
    finally:env.close()
    tmp=out.with_suffix('.tmp')
    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump({'episode':g['episode'],'records':records},f)
    os.replace(tmp,out)
def main():
    mode=sys.argv[1]
    if not (ROOT/'roster.json').exists():save(ROOT/'roster.json',read(ROOT.parent/'roster.json'))
    roster=read(ROOT/'roster.json')
    if mode=='learn':
        hits=collections.defaultdict(collections.Counter);paths=sorted((ROOT/'train').glob('*.gz'))
        assert len(paths)==39
        for f in paths:
            rec=zipread(f)['records'][0]
            for place,names in rec['samples'].items():
                for n in names:hits[n][kind(place)]+=1
        save(ROOT/'learned.json',hits);return
    if mode=='seal':
        paths=[ROOT/p for p in ['actor.py','run.py','PROTOCOL.md','POSE_ADDENDUM.md','roster.json','learned.json']]
        paths+=sorted((ROOT/'train').glob('*.gz'));save(ROOT/'policy_lock.json',{p.relative_to(ROOT).as_posix():sha(p) for p in paths});return
    if mode=='eval':
        assert all(sha(ROOT/k)==v for k,v in read(ROOT/'policy_lock.json').items())
    games=roster['train' if mode in ('dev','train') else 'valid_unseen']
    if mode=='dev':games=games[:6]
    (ROOT/mode).mkdir(exist_ok=True)
    with concurrent.futures.ProcessPoolExecutor(2) as pool:list(pool.map(episode,[(mode,g) for g in games]))
    print(mode,len(games),flush=True)
if __name__=='__main__':main()
