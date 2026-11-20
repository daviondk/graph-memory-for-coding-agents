"""No model, Docker, TextWorld or parent assets needed to independently replay the complete study."""
import collections,csv,gzip,hashlib,json,math,random,sys
from pathlib import Path
from policy_negative import NegativeActor
ROOT=Path(__file__).resolve().parent
ARMS=['baseline','one_step','pose_set']
def read(p):return json.loads(p.read_bytes())
def zread(p):return json.loads(gzip.decompress(p.read_bytes()))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=1),encoding='utf8')
def audit_records():
    for name,h in read(ROOT/'lock.json')['sha256'].items():assert sha(ROOT/name)==h
    roster=read(ROOT/'roster.json');prior=read(ROOT/'learned.json');rows=[];example=[]
    for split,entries in roster.items():
        names={hashlib.sha256(g['episode'].encode()).hexdigest()[:20]+'.json.gz':g for g in entries}
        assert set(names)=={p.name for p in (ROOT/split).glob('*.gz')}
        for name,metadata in names.items():
            trial=zread(ROOT/split/name);assert trial['episode']==metadata['episode']
            records=list(trial['records'])
            if split=='valid_unseen':
                old=zread(ROOT/'baseline_unseen'/name)
                assert old['episode']==trial['episode'] and old['record']['arm']=='trained'
                records.insert(0,{**old['record'],'arm':'baseline'})
            assert [r['arm'] for r in records]==ARMS and len({r['initial'] for r in records})==1
            row={k:metadata[k] for k in ['episode','family','floorplan']};row['split']=split;traces={}
            for rec in records:
                arm=rec['arm'];actor=NegativeActor(rec['initial'],arm,prior);steps=rec['steps']
                assert 0<len(steps)<=50 and (len(steps)==50 or steps[-1][3]) and not any(s[3] for s in steps[:-1])
                active=[];rejections=collections.Counter()
                for command,feedback,won,done,recognized,actual_active in steps:
                    assert actor.action()==command
                    active.append(actor.active)
                    if arm!='baseline' or split=='valid_seen':assert actor.active==actual_active
                    if feedback.strip().lower()=='nothing happens.' and command.startswith('go to '):
                        rejections[(actor.place,command[6:])]+=1
                    assert actor.update(command,feedback)==recognized
                row[arm+'_won']=int(steps[-1][2]);row[arm+'_steps']=len(steps)
                row[arm+'_cost']=len(steps) if steps[-1][2] else 50
                row[arm+'_rejected']=sum(rejections.values())
                row[arm+'_repeat_rejected']=sum(n-1 for n in rejections.values())
                row[arm+'_unconfirmed']=sum(not s[4] for s in steps)
                row[arm+'_peak']=max(active);row[arm+'_active_steps']=sum(n>0 for n in active)
                traces[arm]=[s[0] for s in steps]
            for a,b in [('one_step','baseline'),('pose_set','baseline'),('pose_set','one_step')]:
                row[a+'_'+b+'_identical']=int(traces[a]==traces[b])
                if a=='pose_set' and b=='one_step' and traces[a]!=traces[b]:
                    for i in range(min(len(traces[a]),len(traces[b]))):
                        if traces[a][i]!=traces[b][i]:
                            example.append({'episode':trial['episode'],'step':i+1,'one_step':traces[b][max(0,i-3):i+3],'pose_set':traces[a][max(0,i-3):i+3]});break
            rows.append(row)
    return rows,example
def contrast(rows,a,b):
    def estimate(suffix):
        diffs=[r[a+suffix]-r[b+suffix] for r in rows];floors=collections.defaultdict(list)
        for r,d in zip(rows,diffs):floors[r['floorplan']].append(d)
        clusters=[(sum(x),len(x)) for x in floors.values()];rng=random.Random(20261117);boot=[];cluster=[]
        for _ in range(5000):
            boot.append(sum(rng.choices(diffs,k=len(diffs)))/len(diffs));draw=rng.choices(clusters,k=len(clusters))
            cluster.append(sum(g[0] for g in draw)/sum(g[1] for g in draw))
        boot.sort();cluster.sort()
        return {'delta':sum(diffs)/len(diffs),'task_boot95':[boot[124],boot[4874]],'floorplan_boot95':[cluster[124],cluster[4874]],'positive':sum(d>0 for d in diffs),'negative':sum(d<0 for d in diffs),'ties':diffs.count(0)}
    s=estimate('_won');w=s['positive'];l=s['negative'];n=w+l
    return {'success':s,'cost':estimate('_cost'),'discordant_sign_p':min(1,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/2**n),
            'identical_actions':sum(r[a+'_'+b+'_identical'] for r in rows)}
def group(rows):
    def by_arm(a):
        out={'wins':sum(r[a+'_won'] for r in rows),'steps':sum(r[a+'_steps'] for r in rows),
             'mean_capped_steps':sum(r[a+'_cost'] for r in rows)/len(rows),'peak_negative_entries':max(r[a+'_peak'] for r in rows)}
        for k in ['rejected','repeat_rejected','unconfirmed','active_steps']:out[k]=sum(r[a+'_'+k] for r in rows)
        return out
    return {'n':len(rows),'arms':{a:by_arm(a) for a in ARMS},'floorplans':len({r['floorplan'] for r in rows}),
            'horizon':{str(h):{a:sum(r[a+'_won'] and r[a+'_steps']<=h for r in rows) for a in ARMS} for h in [10,20,30,40,50]},
            'contrasts':{a+'-'+b:contrast(rows,a,b) for a,b in [('one_step','baseline'),('pose_set','baseline'),('pose_set','one_step')]},
            'families':{k:{'n':sum(r['family']==k for r in rows),**{a:sum(r['family']==k and r[a+'_won'] for r in rows) for a in ARMS}} for k in sorted({r['family'] for r in rows})}}
def main():
    rows,examples=audit_records()
    result={s:group([r for r in rows if r['split']==s]) for s in sorted({r['split'] for r in rows})}
    if '--check' in sys.argv:
        assert result==read(ROOT/'results.json') and examples==read(ROOT/'divergences.json')
        for k,h in read(ROOT/'output_lock.json').items():assert sha(ROOT/k)==h
        print('Replayed all physical observations by policy; 134 + 140 paired games verified.');return
    save(ROOT/'results.json',result);save(ROOT/'divergences.json',examples)
    with (ROOT/'per_episode.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    paths=[ROOT/f for f in ('verify.py','per_episode.csv','results.json','divergences.json','lock.json')]+[p for split in result for p in sorted((ROOT/split).glob('*.gz'))]
    save(ROOT/'output_lock.json',{p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    for s,x in result.items():print(s,x['arms'],x['contrasts']['pose_set-one_step'])
if __name__=='__main__':main()
