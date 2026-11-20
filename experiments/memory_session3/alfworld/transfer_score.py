"""Offline runtime outcome checks on the external split and the original floorplan cohort."""
import collections,csv,gzip,hashlib,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(x):return json.loads((ROOT/x).read_bytes())
def main():
    for k,v in read('transfer_lock.json').items():assert hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v
    roster=read('roster.json')['valid_unseen']+read('transfer_seen.json')
    by_ep={g['episode']:g for g in roster};assert len(by_ep)==len(roster)
    arms=['full','rate','all_static','room_static','all_miss','room_miss'];scores={};rows=[]
    for folder in ('traces','transfer_traces'):
        for path in sorted((ROOT/folder).glob('*.gz')):
            for r in json.loads(gzip.decompress(path.read_bytes())):
                ep=r['episode'];a=r['arm']
                if a not in arms:continue
                assert (ep,a) not in scores;steps=r['steps']
                assert len(steps)<=50 and all(s['command'] in s['available'] for s in steps)
                assert not any(s['done'] for s in steps[:-1]) and (steps[-1]['done'] or len(steps)==50)
                win=int(steps[-1]['won']);cost=(len(steps) if win else 50)
                scores[ep,a]=win,cost
                rows.append({**by_ep[ep],'arm':a,'won':win,'capped_steps':cost})
    assert len(scores)==len(arms)*len(roster)
    with (ROOT/'transfer_per_episode.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={}
    def group(eps):
        return {a:{'won':sum(scores[e,a][0] for e in eps),'n':len(eps),'capped_steps_avg':sum(scores[e,a][1] for e in eps)/len(eps)} for a in arms}
    for split in ('valid_seen','valid_unseen'):
        eps=[e for e in by_ep if e.startswith(split+'/')];floor={by_ep[e]['floorplan'] for e in eps}
        summary[split]={'all':group(eps),'floors':{f:group([e for e in eps if by_ep[e]['floorplan']==f]) for f in sorted(floor)},
            'families':{f:group([e for e in eps if by_ep[e]['family']==f]) for f in sorted({by_ep[e]['family'] for e in eps})},'contrasts':{}}
        for b in ['full','rate','all_static','room_static','all_miss']:
            def diff(e,i):return scores[e,'room_miss'][i]-scores[e,b][i]
            rng=random.Random(17112026); groups=[(len(ids),sum(diff(e,0) for e in ids),sum(diff(e,1) for e in ids)) for f in sorted(floor) if (ids:=[e for e in eps if by_ep[e]['floorplan']==f])]
            boot=[[],[]]
            for _ in range(5000):
                draw=rng.choices(groups,k=len(groups));den=sum(g[0] for g in draw)
                for i in range(2):boot[i].append(sum(g[i+1] for g in draw)/den)
            summary[split]['contrasts']['room_miss-'+b]={'win_difference':sum(diff(e,0) for e in eps)/len(eps),
                'step_difference':sum(diff(e,1) for e in eps)/len(eps),'W':sum(diff(e,0)>0 for e in eps),'L':sum(diff(e,0)<0 for e in eps),
                'cluster_intervals':[ [sorted(v)[124],sorted(v)[4874]] for v in boot]}
    (ROOT/'transfer_results.json').write_text(json.dumps(summary,indent=1))
    print({s:x['all'] for s,x in summary.items()})
if __name__=='__main__':main()
