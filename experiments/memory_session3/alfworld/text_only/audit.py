"""Self-contained offline scorer. Regenerates every command from text alone."""
import collections,csv,gzip,hashlib,json,math,random,sys
from pathlib import Path
from actor import Actor,Scout,kind
ROOT=Path(__file__).resolve().parent
ARMS=['none','pose_cycle','cursor','full','trained']
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def zipread(p):return json.loads(gzip.decompress(p.read_bytes()))
def save(p,x):p.write_text(json.dumps(x,indent=1,sort_keys=True),encoding='utf8')
def replay():
    assert all(sha(ROOT/k)==v for k,v in read(ROOT/'policy_lock.json').items())
    roster=read(ROOT/'roster.json');priors=read(ROOT/'learned.json')
    hits=collections.defaultdict(collections.Counter);source=set()
    for f in sorted((ROOT/'train').glob('*.gz')):
        trial=zipread(f);source.add(trial['episode']);rec=trial['records'][0];a=Scout(rec['initial'])
        for command,feedback,won,done,recognized,retained in rec['steps']:
            assert a.action()==command and a.update(command,feedback)==recognized
        if len(rec['steps'])<50 and not rec['steps'][-1][3]:assert a.action() is None
        assert a.samples==rec['samples']
        for p,types in a.samples.items():
            for t in types:hits[t][kind(p)]+=1
    assert {r['episode'] for r in roster['train']}==source and hits==priors
    gold={r['episode']:r for r in roster['valid_unseen']};rows=[]
    action_traces={};nsteps=0
    for f in sorted((ROOT/'eval').glob('*.gz')):
        trial=zipread(f);eid=trial['episode'];g=gold[eid];result={'episode':eid,'floorplan':g['floorplan'],'family':g['family']}
        assert [r['arm'] for r in trial['records']]==ARMS and len({r['initial'] for r in trial['records']})==1
        for rec in trial['records']:
            arm=rec['arm'];a=Actor(rec['initial'],arm,priors);steps=rec['steps'];actions=[];nsteps+=len(steps)
            assert 0<len(steps)<=50 and (len(steps)==50 or steps[-1][3]) and not any(s[3] for s in steps[:-1])
            for command,feedback,won,done,recognized,retained in steps:
                assert a.action()==command and a.update(command,feedback)==recognized
                assert retained==len(a.history)+int(a.cursor is not None)
                actions.append(command)
            action_traces[eid,arm]=actions
            result[arm]=int(steps[-1][2]);result['steps_'+arm]=len(steps)
            result['capped_'+arm]=len(steps) if steps[-1][2] else 50
            result['unrecognized_'+arm]=sum(not s[4] for s in steps)
            result['nothing_'+arm]=sum('nothing happens' in s[1].lower() for s in steps)
            result['max_history_'+arm]=max(s[5] for s in steps)
        rows.append(result)
    assert len(rows)==134 and {r['episode'] for r in rows}==set(gold)
    trace_equal={arm:sum(action_traces[r['episode'],'pose_cycle']==action_traces[r['episode'],arm] for r in rows) for arm in ARMS}
    return rows,nsteps,trace_equal
def contrast(rows,a,b):
    diff=[r[a]-r[b] for r in rows];w=diff.count(1);l=diff.count(-1);n=w+l
    rng=random.Random(20261117)
    byroom=collections.defaultdict(list)
    for r,d in zip(rows,diff):byroom[r['floorplan']].append(d)
    groups=[(sum(g),len(g)) for g in byroom.values()];boot=[];cluster=[]
    for _ in range(5000):
        boot.append(100*sum(rng.choices(diff,k=len(diff)))/len(diff))
        draw=rng.choices(groups,k=len(groups));cluster.append(100*sum(g[0] for g in draw)/sum(g[1] for g in draw))
    boot.sort();cluster.sort()
    return {'wins':w,'losses':l,'ties':len(rows)-n,'delta_pp':100*sum(diff)/len(rows),'paired_task_boot95':[boot[124],boot[4874]],
            'paired_floorplan_cluster95':[cluster[124],cluster[4874]],'floorplans':len(groups),
            'exact_discordance_p':min(1,2*sum(math.comb(n,i) for i in range(min(w,l)+1))/2**n)}
def compute():
    rows,nsteps,equal=replay()
    def group(rs):
        return {'n':len(rs),'arms':{a:{'won':sum(r[a] for r in rs),'attempts':sum(r['steps_'+a] for r in rs),
        'mean_capped_steps':sum(r['capped_'+a] for r in rs)/len(rs),'unrecognized':sum(r['unrecognized_'+a] for r in rs),
        'nothing_happens':sum(r['nothing_'+a] for r in rs),'max_extra_search_entries':max(r['max_history_'+a] for r in rs)} for a in ARMS}}
    def step_difference(a,b):
        diff=[r['capped_'+a]-r['capped_'+b] for r in rows]
        grouped=collections.defaultdict(list)
        for row,d in zip(rows,diff):grouped[row['floorplan']].append(d)
        rooms=[(sum(vals),len(vals)) for vals in grouped.values()]
        rng=random.Random(20261117);means=[];by_room=[]
        for _ in range(5000):
            means.append(sum(rng.choices(diff,k=len(diff)))/len(diff))
            draw=rng.choices(rooms,k=len(rooms))
            by_room.append(sum(g[0] for g in draw)/sum(g[1] for g in draw))
        means.sort();by_room.sort()
        return {'mean_delta_steps':sum(diff)/len(diff),'fewer':sum(d<0 for d in diff),'more':sum(d>0 for d in diff),
                'equal':diff.count(0),'paired_task_boot95':[means[124],means[4874]],'floorplan_boot95':[by_room[124],by_room[4874]]}
    result={'overall':group(rows),'families':{g:group([r for r in rows if r['family']==g]) for g in sorted(set(r['family'] for r in rows))},
      'contrasts':{a+'-'+b:contrast(rows,a,b) for a,b in [('pose_cycle','none'),('cursor','pose_cycle'),('full','pose_cycle'),('trained','full'),('trained','pose_cycle')]},
      'step_contrasts':{a+'-'+b:step_difference(a,b) for a,b in [('pose_cycle','none'),('cursor','pose_cycle'),('full','pose_cycle'),('trained','full'),('trained','pose_cycle')]},
      'identical_to_pose_action_traces':equal,'actual_actions':nsteps}
    result['horizon_sensitivity']={str(h):{a:sum(row[a] and row['steps_'+a]<=h for row in rows) for a in ARMS} for h in (10,20,30,40,50)}
    return rows,result
if __name__=='__main__':
    rows,res=compute()
    if '--check' in sys.argv:
        assert res==read(ROOT/'results.json')
        assert all(sha(ROOT/p)==h for p,h in read(ROOT/'output_lock.json').items())
        print('Verified training + unseen text-only policy replays:',len(rows),'unseen games;',res['actual_actions'],'unseen actions')
    else:
        save(ROOT/'results.json',res)
        with (ROOT/'per_episode.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        paths=[ROOT/f for f in ('audit.py','policy_lock.json','results.json','per_episode.csv')]+sorted((ROOT/'eval').glob('*.gz'))
        save(ROOT/'output_lock.json',{p.relative_to(ROOT).as_posix():sha(p) for p in paths})
        print(res['overall'],res['identical_to_pose_action_traces'])

