"""Rebuild packets from source positions, observed support counts and token costs using exact-weight DP.

No outcome, answer key, text body, terminal rank or learned utility is an input.
"""
import argparse, gzip, hashlib, json, sqlite3
from itertools import combinations
from pathlib import Path

D=Path(__file__).resolve().parent
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def write(p,z):
    raw=(json.dumps(z,sort_keys=True,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix=='.gz' else raw)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def export(db):
    seal=read(D/'input-seal.json')
    assert digest(db)==seal['reader_sha256']
    out={}
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as s:
        for q, in s.execute('select q from query order by q'):
            params=(q,)
            nodes=s.execute('select id,node_hash,tokens from node where q=? order by id',params).fetchall()
            origins=s.execute('select source,position,role from origin where q=? order by source',params).fetchall()
            assignment=s.execute('select distinct id,source from span where q=? order by id,source',params).fetchall()
            out[q]=[nodes,origins,assignment]
    assert len(out)==40
    return json.loads(json.dumps(out))

def exact(ranked,counts,limit):
    # Each label is (objective, negative complete suffix bit mask), compared lexicographically.
    units=[]
    for i,(identity,cost,touched) in enumerate(ranked,1):
        score=((1<<32)+i//2)//i+sum(min(counts[owner],limit)*(1<<28) for owner in touched)
        units.append((identity,cost,score))
    used=0;cut=0
    while cut<len(units) and used+units[cut][1]<=1024:
        used+=units[cut][1];cut+=1
    best={0:(0,0)}
    for k,(_,cost,value) in enumerate(units[cut:]):
        updates={}
        for paid,(score,mask) in best.items():
            extra=paid+cost
            if extra>2048-used:continue
            candidate=(score+value,mask-(1<<k))
            if extra not in best or candidate>best[extra]:
                updates[extra]=candidate
        best.update(updates)
    score,neg=max(best.values())
    selected=units[:cut]+[row for k,row in enumerate(units[cut:]) if ((-neg)>>k)&1]
    return {'ids':[r[0] for r in selected],'tokens':sum(r[1] for r in selected),'utility':score+sum(r[2] for r in units[:cut])}

def replay(q,step,meta,timeline,exhaustive):
    origins={h:(pos,role) for h,pos,role in meta[1]}
    when=dict(timeline['sources'])
    assert set(when)==set(origins)
    owner={p[0]:i for i,p in enumerate(timeline['producers']) if p[0] in origins}
    assert all(origins[h][1]=='tool_output' for h in owner)
    source_by={}
    for i,h in meta[2]:
        assert h in when;source_by.setdefault(i,[]).append(h)
    rows=[]
    for ident,key,price in meta[0]:
        fields=source_by.get(ident,[])
        if not fields or any(when[h]>step for h in fields):continue
        positions=[origins[h][0] for h in fields]
        rows.append(((-max(positions),-min(positions),key),(ident,price,sorted({owner[h] for h in fields if h in owner}))))
    ranked=[u for _,u in sorted(rows)]
    counts=[0]*len(timeline['producers'])
    for frame in timeline['steps'][:step-1]:
        for ident,pre,post in frame[2]:
            assert pre==counts[ident] and post>=0;counts[ident]=post
    changes=timeline['steps'][step-1][2]
    assert all(counts[i]==a and b>=0 and b!=a for i,a,b in changes)
    m=len(changes);allmask=(1<<m)-1
    masks=range(1<<m) if exhaustive else sorted({0,allmask,*(1<<i for i in range(m))})
    cases={}
    for limit in (1,4):
        packets=[]
        for mask in masks:
            now=counts.copy()
            for k,(j,before,after) in enumerate(changes):
                if mask&(1<<k):now[j]=after
            packets.append([mask,exact(ranked,now,limit)])
        changed=[mask for mask,p in packets if p['ids']!=packets[0][1]['ids']]
        record={'packets':packets}
        if exhaustive:
            record['minimal_change_masks']=[mask for mask in changed if all(other==mask or other&mask!=other for other in changed)]
            record['full_packet_matches']=sum(p['ids']==packets[-1][1]['ids'] for _,p in packets)
        cases[str(limit)]=record
    return {'q':q,'step':step,'changes':changes,'eligible_candidates':len(ranked),'cases':cases}

def main():
    p=argparse.ArgumentParser();p.add_argument('--export',type=Path);p.add_argument('--write',action='store_true');args=p.parse_args()
    src=D/'reader-columns.json.gz';fixture=D.parent/'observed_join/projection.json.gz'
    reg=read(D/'input-seal.json')
    assert digest(fixture)==reg['projection_sha256'] and digest(D/'PROTOCOL_RU.md')==reg['protocol_sha256']
    if args.export:
        cols=export(args.export)
        if src.exists():assert read(src)==cols
        elif args.write:write(src,cols)
    data=read(src);proj=read(fixture)['queries']
    q,step=reg['example'];main_case=replay(q,step,data[q],proj[q],True)
    assert len(main_case['changes'])==6
    controls=[]
    for key,trace in sorted(proj.items()):
        pos=min(range(1,len(trace['steps'])+1),key=lambda i:hashlib.sha256(f"{reg['salt']}|{key}|{i}".encode()).digest())
        controls.append(replay(key,pos,data[key],trace,False))
    out={'example':main_case,'controls':controls,'distinct_queries':len(data),'metadata_sha256':digest(src)}
    target=D/'results.json.gz'
    if args.write:write(target,out)
    assert read(target)==out
    for limit,z in main_case['cases'].items():
        print('cap',limit,'base',z['packets'][0][1]['ids'],'full',z['packets'][-1][1]['ids'],'minimal',z['minimal_change_masks'],'matches',z['full_packet_matches'])
    print(len(controls),'deterministic control groups')
if __name__=='__main__':main()
