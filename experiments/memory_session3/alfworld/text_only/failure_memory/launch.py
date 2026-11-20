"""Frozen, physical CPU rollouts. Split metadata is kept outside the actor."""
from pathlib import Path
import collections,concurrent.futures,datetime,gzip,hashlib,json,os,sys
ROOT=Path(__file__).resolve().parent;TEXT=ROOT.parent;ENV=TEXT.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=1),encoding='utf8')
def zread(p):return json.loads(gzip.decompress(p.read_bytes()))
def zsave(p,x):
    tmp=p.with_suffix('.tmp')
    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump(x,f)
    os.replace(tmp,p)
def seal():
    for p in ['actor.py','learned.json']:
        dest=ROOT/('base_actor.py' if p=='actor.py' else p)
        dest.write_bytes((TEXT/p).read_bytes())
    rosters={'valid_unseen':read(TEXT/'roster.json')['valid_unseen'],'valid_seen':read(ENV/'transfer_seen.json')}
    assert [len(rosters['valid_unseen']),len(rosters['valid_seen'])]==[134,140]
    save(ROOT/'roster.json',rosters)
    controls=ROOT/'baseline_unseen';controls.mkdir(exist_ok=True);origin={}
    top=read(TEXT/'output_lock.json')
    for p in sorted((TEXT/'eval').glob('*.gz')):
        assert top['eval/'+p.name]==sha(p)
        d=zread(p);r=next(record for record in d['records'] if record['arm']=='trained')
        zsave(controls/p.name,{'episode':d['episode'],'record':r});origin[p.name]=sha(p)
    save(ROOT/'baseline_origin.json',origin)
    fs=['PROTOCOL.md','policy_negative.py','launch.py','base_actor.py','learned.json','roster.json','baseline_origin.json']
    paths=[ROOT/f for f in fs]+sorted(controls.glob('*.gz'))
    save(ROOT/'lock.json',{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in paths}})
def run(g):
    from policy_negative import NegativeActor
    sys.path.insert(0,str(ENV))
    from engine import DATA,AlfredDemangler,textworld
    prior=read(ROOT/'learned.json')
    eid=g['episode'];split=eid.split('/')[0];name=hashlib.sha256(eid.encode()).hexdigest()[:20]+'.json.gz'
    out=ROOT/split/name
    if out.exists():return
    assert sha(DATA/eid)==g['game_sha']
    game=textworld.start(str(DATA/eid),textworld.EnvInfos(won=True),wrappers=[AlfredDemangler])
    records=[]
    try:
        for arm in (['one_step','pose_set'] if split=='valid_unseen' else ['baseline','one_step','pose_set']):
            s=game.reset();actor=NegativeActor(s.feedback,arm,prior);record={'arm':arm,'initial':s.feedback,'steps':[]}
            for _ in range(50):
                action=actor.action();active=actor.active
                s,reward,done=game.step(action);recognized=actor.update(action,s.feedback)
                record['steps'].append([action,s.feedback,bool(s.won),bool(done),recognized,active])
                if done:break
            records.append(record)
    finally:game.close()
    zsave(out,{'episode':eid,'records':records})
def main():
    if sys.argv[1]=='seal':seal();return
    for p,h in read(ROOT/'lock.json')['sha256'].items():assert sha(ROOT/p)==h
    roster=read(ROOT/'roster.json')
    for split in roster:(ROOT/split).mkdir(exist_ok=True)
    # Interleave the two pre-locked splits to mitigate run-order effects. No partial scoring or adaptation.
    games=sorted(sum(roster.values(),[]),key=lambda g:hashlib.sha256(('negative-v1'+g['episode']).encode()).hexdigest())
    with concurrent.futures.ProcessPoolExecutor(4) as pool:list(pool.map(run,games))
    print('Completed',len(games),'games',flush=True)
if __name__=='__main__':main()
