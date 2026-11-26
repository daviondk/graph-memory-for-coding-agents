"""Independent exact checks (no NumPy/compiler required). Tie order is part of the score."""
import argparse,itertools,random
from build import load,save
from geometry import INF,LIMIT,probes,policies

def best(rows,cap,x,y):
    states=[(0,0)]*(cap+1)
    for i,(cost,u,a,b) in enumerate(rows):
        delta=u+a*x+b*y;bit=1<<i
        previous=states.copy()
        for budget in range(cost,cap+1):
            value,mask=previous[budget-cost]
            states[budget]=max(previous[budget],(value+delta,mask-bit))
    return -states[cap][1]
def exact_axes(choices,base,axis):
    lo,hi=-INF,INF
    chosen=next(v for v in choices if v[0]==base)
    for row in choices:
        if row==chosen:continue
        slope=row[axis]-chosen[axis]
        gain=chosen[1]-row[1]-int(row[0]<base)
        if slope>0:hi=min(hi,gain//slope)
        elif slope<0:lo=max(lo,-((-gain)//slope))
        else:assert gain>=0
    return lo,hi
def synth():
    rng=random.Random(470638);count=preserved=accepted=wrong_box=unbounded=zero_radius=0
    for rep in range(160):
        n=rng.randint(3,8);cap=rng.randint(3,9)
        rows=[[rng.randint(1,3),rng.randint(-4,5),rng.randrange(2),rng.randrange(2)] for _ in range(n)]
        rows[0][2:]=[1,1]
        choices=[]
        for mask in range(1<<n):
            price,utility,a,b=map(sum,zip((0,0,0,0),*[r for i,r in enumerate(rows) if mask&(1<<i)]))
            if price<=cap:choices.append((mask,utility,a,b))
        def full(x,y):
            return max(choices,key=lambda r:(r[1]+x*r[2]+y*r[3],-r[0]))[0]
        old=full(0,0);ix=exact_axes(choices,old,2);iy=exact_axes(choices,old,3)
        unbounded+=int(INF in (*ix,*iy) or -INF in (*ix,*iy))
        zero_radius+=int(0 in (*ix,*iy))
        for x,y in itertools.product(range(-5,6),repeat=2):
            actual=full(x,y);same=actual==old;box,cut,hull,fav=policies(x,y,ix,iy)
            assert not (hull or cut or fav) or same
            assert best(rows,cap,x,y)==actual
            count+=1;preserved+=same;accepted+=hull;wrong_box+=int(box and not same)
    return dict(pools=160,intersections=160,points=count,preserved=preserved,certified=accepted,unsafe_box=wrong_box,unbounded_pools=unbounded,zero_radius_pools=zero_radius)
def check_real():
    sample=load('sample.json.gz');forecasts=load('joint-outcomes.json.gz');positions=0;max_profit=0
    for q,s in sample.items():
        max_profit=max(max_profit,sum(abs(u) for _,_,u in s['tail'])+1)
        for pair,obs in zip(s['pairs'][:2],forecasts[q][:2]):
            a,b,_=pair;src=set(s['source'][a]);dest=set(s['source'][b]);rows=[(c,u,int(i in src),int(i in dest)) for i,c,u in s['tail']]
            m,d=probes(s['limits'][a],s['limits'][b]);grid=[(0,0),*m,*d]
            for xy in [(0,0),(LIMIT,LIMIT),(-LIMIT,LIMIT),d[len(d)//2]]:
                chosen=best(rows,s['cap'],*xy);i=grid.index(xy)
                reconstructed=sum((1<<r) for r,k in enumerate(obs['table'][obs['idx'][i]]) if k=='1')
                assert reconstructed==chosen;positions+=1
    assert max_profit<INF//2
    return dict(real_verifications=positions,trajectories=len(sample),max_finite_limit_bound=max_profit)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args()
    out={'real':check_real(),'overlap':synth()}
    if args.write:save('independent.json',out)
    assert load('independent.json')==out
    print(out)
