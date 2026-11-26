"""Independently enumerate feasible packets in a small finite domain."""
from collections import Counter
from itertools import product
from pathlib import Path
import argparse, gzip, hashlib, json, random
from envelope import LOW, HIGH, make_envelope

D=Path(__file__).resolve().parent
GRID=range(LOW,HIGH+1)

def feasible(items,budget):
    choices=[]
    for mask in range(1<<len(items)):
        cost,base,a,b=map(sum,zip((0,0,0,0),*(row for i,row in enumerate(items) if (mask>>i)&1)))
        if cost<=budget:choices.append((mask,base,a,b))
    return choices

def limits(chosen, axis):
    baseline=chosen[0,0]
    same=[v for v in GRID if chosen[(v,0) if axis==0 else (0,v)]==baseline]
    assert same==list(range(min(same),max(same)+1))
    return min(same),max(same)

def assess(items,budget):
    choices=feasible(items,budget)
    def solve(x,y):
        return max(choices,key=lambda row:(row[1]+x*row[2]+y*row[3],-row[0]))
    winners={(x,y):solve(x,y)[0] for x,y in product(GRID,repeat=2)}
    truth=winners[0,0]
    spans=[]
    for axis in (0,1):
        def scalar(delta):
            row=solve(delta,0) if axis==0 else solve(0,delta)
            return row[0],row[1],row[axis+2]
        found,calls=make_envelope(scalar)
        assert {v:p for lo,hi,p in found for v in range(lo,hi+1)}=={v:winners[(v,0) if axis==0 else (0,v)] for v in GRID}
        assert all(l[1]+1==r[0] and l[2]!=r[2] for l,r in zip(found,found[1:]))
        spans.append((found,calls))
    ax,ay=limits(winners,0),limits(winners,1)
    counts=Counter()
    for (x,y),mask in winners.items():
        same=mask==truth
        box=ax[0]<=x<=ax[1] and ay[0]<=y<=ay[1]
        rx=abs(ax[int(x>0)]);ry=abs(ay[int(y>0)])
        inside=box and (not x or not y or abs(x)*ry+abs(y)*rx<=rx*ry)
        counts['grid']+=1;counts['same']+=int(same)
        for method,accept in [('box',box),('hull',inside)]:
            counts[method+'_accepted']+=int(accept)
            counts[method+'_false']+=int(accept and not same)
        assert not inside or same
    return dict(items=items,budget=budget,axis=spans,base=truth,grid_masks=[winners[x,y] for x,y in product(GRID,repeat=2)],counts=dict(counts))

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');opts=p.parse_args()
    rng=random.Random(460911);rows=[]
    for _ in range(320):
        n=rng.randint(4,8);budget=rng.randint(3,10)
        rows.append(assess([[rng.randint(1,4),rng.randint(-2,6),rng.randrange(2),rng.randrange(2)] for _ in range(n)],budget))
    singleton=assess([[2,6,1,0],[2,6,0,0],[1,3,1,0],[1,3,1,0]],2)
    assert singleton['axis'][0][0]==[(-4,-1,2),(0,0,1),(1,4,12)]
    cartesian=assess([[2,5,0,0],[1,2,1,0],[1,2,0,1]],2)
    mid=lambda x,y:cartesian['grid_masks'][(x-LOW)*9+y-LOW]
    assert [mid(0,0),mid(1,0),mid(0,1),mid(1,1)]==[1,1,1,6]
    counts=sum((Counter(r['counts']) for r in rows),Counter())
    assert not counts['hull_false'] and counts['box_false']>0
    totals=dict(counts);totals['hull_false']=0
    record={'pools':len(rows),'axis_points':2*len(rows)*len(GRID),'counts':totals,'box_false_pools':sum(r['counts']['box_false']>0 for r in rows),'singleton_intervals':singleton['axis'][0][0],'two_source_example':[1,1,1,6]}
    for name,data in [('pools.json.gz',rows),('results.json',record)]:
        raw=(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
        if opts.write:(D/name).write_bytes(gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw)
        other=(D/name).read_bytes()
        assert (gzip.decompress(other) if name.endswith('.gz') else other)==raw
    print(json.dumps(record))
if __name__=='__main__':main()
