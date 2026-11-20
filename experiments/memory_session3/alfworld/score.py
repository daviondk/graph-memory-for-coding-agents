"""Offline scoring from complete public action traces. Refuses to score an incomplete family."""
import csv,collections,gzip,hashlib,itertools,json,math,random
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(n):return json.loads((ROOT/n).read_bytes())
def main():
    roster=read('roster.json'); games={x['episode']:x for x in roster['valid_unseen']};assert len(games)==134
    assert not ({x['floorplan'] for x in roster['train']} & {x['floorplan'] for x in games.values()})
    arms=['none','recent','cursor','full','raw','rate','q_prior','q_shown','q_placebo','q_fused']
    floorplans=sorted({g['floorplan'] for g in games.values()})
    def traces(folder):
        for f in sorted((ROOT/folder).glob('*.gz')):yield from json.loads(gzip.decompress(f.read_bytes()))
    for n in ['lock.json','planner_input_lock.json','planner_lock.json']:
        for k,h in read(n).items():assert hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==h
    data={};starts={}
    for record in itertools.chain(traces('traces'),traces('planner_traces')):
        ep=record['episode']; a=record['arm'];steps=record['steps'];g=games[ep];assert 0<len(steps)<=50
        assert not any(x['done'] for x in steps[:-1]); assert all(x['command'] in x['available'] for x in steps)
        assert steps[-1]['won'] or len(steps)==50 or steps[-1]['done']
        pair=ep,a;assert pair not in data and a in arms
        assert starts.setdefault(ep,record['initial'])==record['initial']
        attempts=[s['searched'] for s in steps if s['searched']]
        data[pair]={'episode':ep,'arm':a,'floorplan':g['floorplan'],'family':g['family'],'win':int(steps[-1]['won']),
            'cost':len(steps) if steps[-1]['won'] else 50,'commands':len(steps),'repeat_checks':len(attempts)-len(set(attempts)),
            'peak_search_entries':max(s['retained_search_entries'] for s in steps)}
    assert len(data)==len(arms)*len(games)
    with (ROOT/'per_episode.csv').open('w',encoding='utf8',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(next(iter(data.values()))));w.writeheader();w.writerows(data.values())
    def group(eps):
        return {a:{'won':sum(data[e,a]['win'] for e in eps),'n':len(eps),'step_sum':sum(data[e,a]['cost'] for e in eps),
            'mean_capped_steps':sum(data[e,a]['cost'] for e in eps)/len(eps),'repeated_checks':sum(data[e,a]['repeat_checks'] for e in eps),
            'max_retained_search_entries':max(data[e,a]['peak_search_entries'] for e in eps)} for a in arms}
    def contrast(a,b):
        def paired(e):return (data[e,a]['win']-data[e,b]['win'],data[e,a]['cost']-data[e,b]['cost'])
        floor={f:[paired(e) for e,g in games.items() if g['floorplan']==f] for f in floorplans}
        flat=list(itertools.chain.from_iterable(floor.values()));wins=sum(s>0 for s,c in flat);losses=sum(s<0 for s,c in flat);n=wins+losses
        # Enumerate every equally likely resampling of four floorplan clusters (4^4); aggregate episode-weighted.
        bs=[[],[]]
        for draw in itertools.product(floorplans,repeat=len(floorplans)):
            sample=list(itertools.chain.from_iterable(floor[f] for f in draw))
            for col in range(2):bs[col].append(sum(x[col] for x in sample)/len(sample))
        ci=[(sorted(x)[int(.025*(len(x)-1))],sorted(x)[int(.975*(len(x)-1))]) for x in bs]
        return {'W':wins,'L':losses,'T':len(flat)-n,'win_difference':(wins-losses)/len(flat),
            'mean_step_difference':sum(c for s,c in flat)/len(flat),'floor_resample_win_interval':ci[0],
            'floor_resample_steps_interval':ci[1],'episode_sign_p_descriptive':min(1,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/2**n),
            'floor_differences':{f:{'n':len(x),'net_wins':sum(s for s,c in x),'step_sum_difference':sum(c for s,c in x)} for f,x in floor.items()}}
    costs=collections.Counter();finish=collections.Counter()
    for f in sorted((ROOT/'planner_calls').glob('*.json')):
        c=read(f.relative_to(ROOT));rep=c['response'];costs.update({k:rep['usage'][k] for k in ('prompt_tokens','completion_tokens')});finish.update([rep['choices'][0]['finish_reason']])
    plans=read('plans.json');defaulted=sum(r['missing']>0 for r in plans.values())
    result={'all':group(games),'contrasts':{a+'-'+b:contrast(a,b) for a,b in [('full','recent'),('cursor','full'),('rate','full'),('rate','raw'),('q_shown','q_prior'),('q_shown','q_placebo'),('q_fused','q_prior')]},
            'families':{f:group([e for e,g in games.items() if g['family']==f]) for f in sorted({x['family'] for x in games.values()})},
            'floors':{f:group([e for e,g in games.items() if g['floorplan']==f]) for f in floorplans},'train_n':len(roster['train']),
            'training_steps':sum(len(r['steps']) for r in traces('train_logs')),'search_observations':sum(read('learned.json')['seen'].values()),
            'eval_steps':sum(r['commands'] for r in data.values()),'planner_usage':dict(costs),'planner_native_calls':sum(finish.values()),
            'planner_finishes':dict(finish),'planner_queries_missing_at_least_one_class':defaulted}
    (ROOT/'results.json').write_text(json.dumps(result,indent=1))
    print(json.dumps(result['all'],indent=1))
if __name__=='__main__':main()
