"""Pure event-list oracle for fixed-size memory. No calls to the database or its encoders."""
from collections import Counter,defaultdict,deque
import argparse
from hashlib import sha256
from bench import BUDGETS,FIXED,HERE,PANELS,io,project

def width(n):
    return max(1,(n.bit_length()+6)//7)

def member_len(ids):
    return sum(width(y-x) for x,y in zip((-1,*ids),ids))

def rec_len(weight,peers):
    length=member_len(peers)
    return width(weight)+width(length)+length

def keep(mode,state,peers,budget,events):
    if mode=='space':
        for p in peers:
            if p in state:
                state[p]+=1
            elif len(state)<budget//4:
                state[p]=1
            else:
                lo,idx=min((c,-i) for i,c in state.items())
                del state[-idx];state[p]=lo+1
        return state
    if mode=='lossy':
        for p in peers:
            state[p]=state.get(p,0)+1
            while member_len(sorted(state))+sum(map(width,state.values()))>budget:
                worst=min((c,-i) for i,c in state.items())
                del state[-worst[1]]
        return state
    if not peers and mode!='raw':
        return state
    if rec_len(1,peers)>budget:
        events['too_large_new_observations']+=1
        return state
    if state and state[0][1]==peers and mode=='runs':
        n=state[0][0]+1
        if rec_len(n,peers)<=budget:
            state[0]=(n,peers)
        events['merged_runs']+=1
    else:
        state.insert(0,(1,peers))
    size=sum(rec_len(n,s) for n,s in state)
    while size>budget:
        removed=state.pop();size-=rec_len(*removed)
    return state

def audit():
    frozen=io(HERE/'fixed-ranks.json.gz')
    checks=Counter()
    diagnostics=defaultdict(Counter)
    for panel,source in PANELS.items():
        for repo,raw in io(source/'commits.json.gz').items():
            corpus,tops=project(raw)
            for b in BUDGETS:
                for m in FIXED:
                    state={}
                    freq=Counter();window=deque()
                    for t,(_,nodes,born,q) in enumerate(corpus):
                        if q:
                            a,g=q
                            loaded=state.get(a,{})
                            if m in ('space','lossy'):counts=loaded
                            else:
                                counts=Counter()
                                for multiplicity,ids in loaded:
                                    for v in ids:counts[v]+=multiplicity
                            ranked=sorted((i for i in state if i!=a),key=lambda i:(-counts.get(i,0), -freq[i],i))[:8]
                            assert ranked==frozen[panel][repo][m+str(b)][str(t)]
                            checks['bounded_rank_lists']+=1
                        for a in nodes:
                            initial={} if m in ('space','lossy') else []
                            peers=tuple(p for p in nodes if p!=a)
                            state[a]=keep(m,state.get(a,initial),peers,b,diagnostics[panel+'_'+m+str(b)])
                        freq.update(nodes)
                        window.append(nodes)
                        if len(window)>32:freq.subtract(window.popleft())
                    checks['project_backend_budget_replays']+=1
    return dict(checks=checks,diagnostics=diagnostics)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true')
    d=audit()
    if p.parse_args().verify:assert d==io(HERE/'fixed-audit.json')
    else:io(HERE/'fixed-audit.json',d)
    print(d['checks'])
