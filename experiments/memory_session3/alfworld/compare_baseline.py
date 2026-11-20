"""Post-hoc estimate for the same pre-existing static training prior on the two completed splits."""
import csv,json,random
from collections import defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent
def main():
    with (P/'transfer_per_episode.csv').open(encoding='utf8') as f:rows=list(csv.DictReader(f))
    out={}
    for split in ('valid_seen','valid_unseen'):
        eps=defaultdict(dict)
        for r in rows:
            if r['episode'].startswith(split+'/'):eps[r['episode']][r['arm']]=r
        grouped=defaultdict(list)
        for v in eps.values():
            old,new=v['full'],v['rate']
            grouped[old['floorplan']].append(int(new['capped_steps'])-int(old['capped_steps']))
        units=[(len(ds),sum(ds)) for key,ds in sorted(grouped.items())];rng=random.Random(17112026)
        estimates=[]
        for _ in range(10000):
            draw=rng.choices(units,k=len(units));estimates.append(sum(x[1] for x in draw)/sum(x[0] for x in draw))
        estimates.sort()
        out[split]={'episodes':len(eps),'rooms':len(units),'rooms_lower_steps':sum(d<0 for n,d in units),'rooms_higher_steps':sum(d>0 for n,d in units),'mean_step_delta':sum(d for n,d in units)/len(eps),'room_paired_interval':[estimates[249],estimates[9749]]}
    (P/'paired_rate_full.json').write_text(json.dumps(out,indent=1));print(out)
if __name__=='__main__':main()
