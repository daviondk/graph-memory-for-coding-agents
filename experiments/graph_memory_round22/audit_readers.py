"""Post-freeze independent audit, reads existing forecasts. No language-model calls."""
from collections import Counter, defaultdict
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sqlite3
import statistics
import sys

D=Path(__file__).resolve().parent
P=D/'prefix_read'
A=D/'action_reader'
O=D/'observed_flow'
DEMO=D.parent/'graph_memory_round21/provenance_demo'
RANK=D.parent/'graph_memory_round19/trained_rank'
sys.path.insert(0,str(O))
from build_packets import entity, order
from sources import C


def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)


def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def key(s):
    return s['event_id'],s['json_pointer']


def merge(parts):
    spans=[]
    for a,b in sorted(parts):
        if spans and spans[-1][1]>=a:
            spans[-1]=(spans[-1][0],max(b,spans[-1][1]))
        else:
            spans.append((a,b))
    assert all(a<b for a,b in spans)
    return spans


def min_cost(gold, candidates):
    # Project onto the concatenation of gold intervals. A source chunk covers a
    # contiguous interval there. DP enumerates reachable right endpoints.
    def projected(pos):
        return sum(max(0,min(pos,b)-a) for a,b in gold)
    target=sum(b-a for a,b in gold)
    edges=[(projected(a),projected(b),cost) for a,b,cost in candidates]
    dp={0:0}
    for e in sorted({0}|{b for _,b,_ in edges}):
        if e in dp:
            for lo,hi,w in edges:
                if lo<=e<hi:
                    dp[hi]=min(dp.get(hi,math.inf),dp[e]+w)
    return dp.get(target,math.inf)


def self_test():
    # Compare the DP with exhaustive subset enumeration on small overlapping inputs.
    examples=(((1,3),(6,7)),((1,4),),((1,3),(4,5)))
    options=[(0,2,5),(1,6,10),(2,5,1),(2,8,5),(6,7,1),(7,10,1)]
    n=0
    for run in range(1,len(options)+1):
        for pool in itertools.combinations(options,run):
            for gold in examples:
                points={j for a,b in gold for j in range(a,b)}
                best=math.inf
                for k in range(len(pool)+1):
                    for sub in itertools.combinations(pool,k):
                        covered={j for a,b,_ in sub for j in range(a,b)}
                        if points<=covered:best=min(best,sum(w for _,_,w in sub))
                assert min_cost(gold,pool)==best
                n+=1
    return n


def prefix():
    gold=read(D.parent/'graph_memory_round18/isetrace_official/gold-spans.json.gz')
    observed={(r['q'],r['cut']):r for r in read(P/'outcomes.json.gz')}
    populations=defaultdict(Counter)
    upper=defaultdict(list)
    cert=defaultdict(Counter)
    for shard in range(8):
        dense={r['q']:r for r in read(RANK/f'forecasts-main-{shard}.json.gz')}
        by=defaultdict(list)
        for row in read(P/f'forecast-{shard}.json.gz'):
            by[row['q']].append(row)
        for q,rows in by.items():
            r=dense[q];chunks=r['rr']
            group=defaultdict(list)
            for s in gold[q]:group[key(s)].append((s['char_start'],s['char_end']))
            gs={k:merge(v) for k,v in group.items()}
            by_event=defaultdict(list)
            for i,c in enumerate(chunks):
                assert len(c['source_spans'])==1
                s=c['source_spans'][0];k=key(s)
                if k in gs:
                    by_event[k].append((i,s['char_start'],s['char_end'],c['token_count']))
            costs={k:min_cost(span,[(a,b,w) for i,a,b,w in by_event[k]]) for k,span in gs.items()}
            total=sum(costs.values())
            for row in rows:
                selected=set(row['available']);obs=observed[q,row['cut']]
                available={}
                for k,inds in by_event.items():
                    avail={i for i,a,b,w in inds}&selected
                    assert not avail or len(avail)==len(inds)
                    available[k]=bool(avail)
                reachable=all(available.get(k,False) for k in gs) and math.isfinite(total)
                assert obs['eligible']==reachable
                admitted=reachable and total<=2048
                for sig in [f"{row['cut']}/all"]+([] if row['pilot'] else [f"{row['cut']}/outside_pilot"]):
                    populations[sig]['n']+=1
                    populations[sig]['visible']+=int(reachable)
                    populations[sig]['fit_2048']+=int(admitted)
                    if reachable:upper[sig].append(total)
                    if admitted:
                        for m in obs['arms']:
                            cert[sig][m]+=obs['arms'][m]['fs']
                assert not any(x['fs'] for x in obs['arms'].values()) or admitted
    return {k:dict(c,observed_hits_on_budget_feasible=cert[k],min_cost_max=max(upper[k]),
                   min_cost_median=statistics.median(upper[k])) for k,c in sorted(populations.items())}


def actions():
    cards=read(A/'cards.json.gz'); prompts=read(A/'requests.json.gz')
    lock=read(A/'selection-lock.json')
    assert lock['cards']==h(A/'cards.json.gz') and lock['requests']==h(A/'requests.json.gz')
    regex=re.compile(r'Read one source\. The four candidates are:\nA: age=\d{6} names=\d{3} values=\d{3} last=[01]\nB: age=\d{6} names=\d{3} values=\d{3} last=[01]\nC: age=\d{6} names=\d{3} values=\d{3} last=[01]\nD: age=\d{6} names=\d{3} values=\d{3} last=[01]')
    assert all(regex.fullmatch(t) for t in prompts.values())
    levels=Counter();uses=defaultdict(list)
    for c in cards:
        a,b=c['arms']['fifo'],c['arms']['name_index']
        assert all(x['producer']<c['step'] for arm in (a,b) for x in arm['cards'])
        levels[len({x['producer'] for x in a['cards']}&{x['producer'] for x in b['cards']})]+=1
        for label,arm in c['arms'].items():
            for orientation,p in arm['prompts'].items():uses[p].append((c['family'],c['case'],label,orientation))
    typed=Counter()
    for entry in read(O/'corpus-audit.json'):
        if entry['status']!='eligible':continue
        obj=read(C/(entry['blob']+'.json')); writers=defaultdict(set)
        actions={order(k) for k in obj['activity']};actions.discard(None)
        for z in obj['wasGeneratedBy'].values():
            j=order(z.get('prov:activity',''))
            if j in actions:writers[z['prov:entity']].add(j)
        for e,v in obj['entity'].items():
            if entity(v) is not None:typed[len(writers[e])]+=1
    return dict(cases=len(cards),families=len({c['family'] for c in cards}),overlap_counts=levels,
                directed_requests=sum(map(len,uses.values())),unique_prompts=len(uses),
                prompt_keys_used_in_several_cases=sum(len({z[1] for z in v})>1 for v in uses.values()),
                prompt_keys_used_in_several_families=sum(len({z[0] for z in v})>1 for v in uses.values()),
                acquisition_selected_max=max(Counter(c['family'] for c in cards).values()),typed_scalars_by_generator_count=typed)


def released_strings():
    with sqlite3.connect((DEMO/'provenance.sqlite').resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        txt=Counter()
        for tab in ['trace','event','endpoint','witness','reason','checkpoint']:
            cols=db.execute('PRAGMA table_info('+tab+')').fetchall()
            for _,n,kind,*_ in cols:
                if kind=='TEXT':
                    vals=[v[0] for v in db.execute('SELECT DISTINCT '+n+' FROM '+tab)]
                    if n=='t':assert all(re.fullmatch(r'traj_[a-f0-9]{16}',v) for v in vals)
                    elif n=='kind':assert set(vals)=={'message','tool_call','tool_output'}
                    elif n=='cause':assert set(vals)=={'ambiguous','match'}
                    else:raise AssertionError((tab,n))
                    txt[tab+'.'+n]=len(vals)
        assert not db.execute('PRAGMA freelist_count').fetchone()[0]
    page=(DEMO/'explorer.html').read_text('utf8')
    inline=json.loads(re.search(r'const histories=(\[.*?\]);\s*async function fetchJSON',page,re.DOTALL)[1])
    types=Counter()
    for tr in inline:
        assert set(tr)=={'t','e','w','p','c','why'} and re.fullmatch(r'traj_[a-f0-9]{16}',tr['t'])
        for coll in ('e','w','p','c','why'):
            for row in tr[coll]:
                for j,x in enumerate(row):
                    if isinstance(x,str):
                        assert coll=='why' and j==4 and x in {'ambiguous','match'}
                        types[x]+=1
                    else:assert x is None or type(x) is int
    return dict(exposed_string_fields=txt,embedded_histories=len(inline),json_values_text_whitelist=types)


def query_overlap():
    splits=read(RANK/'split.json.gz')
    src=Path('D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl')
    def take(line):
        r=json.loads(line)
        return r['id'],hashlib.sha256(' '.join(r['query'].lower().split()).encode()).hexdigest()
    with src.open('rb') as f:
        normals=dict(take(line) for line in f)
    with src.with_suffix('.jsonl.metadata.jsonl').open('rb') as f:
        meta={z['query_id']:z['task_key'] for raw in f if (z:=json.loads(raw))}
    report={}
    for field,mapper in [('question_id',lambda r:r['q']),('trajectory',lambda r:r['t']),
                         ('official_task_key',lambda r:meta[r['q']]),('normalized_question',lambda r:normals[r['q']])]:
        groups={s:{mapper(r) for r in v} for s,v in splits.items()}
        report[field]={'train':len(groups['train']),'dev':len(groups['dev']),'test':len(groups['test']),
                       'test_seen_in_train_or_dev':len(groups['test'] & (groups['dev']|groups['train']))}
    return report


def verify_actions():
    cards=read(A/'cards.json.gz')
    choices=read(A/'choices.json.gz')
    cases={z['case']:z for z in read(A/'outcomes.json.gz')}
    truth=defaultdict(set)
    for tr in read(C/'flow-gold.json'):
        for z in tr['reads']:
            truth[tr['trace'],z['consumer']].add(z['producer'])
    with sqlite3.connect(':memory:') as db:
        db.execute('create table writes(trace text, eid int, payload blob, primary key(trace,eid)) without rowid')
        for tr in read(C/'flow-packets.json'):
            for ev in tr['events']:
                if ev['write']:
                    payload=json.dumps(ev['write'],separators=(',',':')).encode()
                    db.execute('insert into writes values(?,?,?)',(tr['trace'],ev['id'],payload))
        db.commit()
        sums=Counter();fam=Counter();dist=Counter();n=0
        lengths=defaultdict(list)
        for row in cards:
            t,step=row['t'],row['step'];gold=truth[t,step];saved=cases[row['case']]
            assert len(gold)==saved['n_targets']
            by_arm={}
            for name,arm in row['arms'].items():
                for orient,msg in arm['prompts'].items():
                    label=name+'/'+orient;sub=arm['cards'] if orient=='normal' else arm['cards'][::-1]
                    p=sub['ABCD'.index(choices[msg]['letter'])]['producer']
                    assert p==saved['actions'][label]
                    value=db.execute('select payload from writes where trace=? and eid=?',(t,p)).fetchone()[0]
                    assert hashlib.sha256(value).hexdigest()==saved['returned_write_hashes'][label]
                    lengths[label].append(len(value))
                    v=int(p in gold);assert v==saved['arms'][label]
                    if gold:sums[label]+=v
                    by_arm[label]=v
                    n+=1
            if gold:
                diff=by_arm['name_index/normal']-by_arm['fifo/normal']
                fam[row['family']]+=diff
                dist[diff]+=1
        observed=sum(fam.values())
        active=[v for v in fam.values() if v]
        null=[sum(i*v for i,v in zip(s,active)) for s in itertools.product((-1,1),repeat=len(active))]
        p=sum(abs(v)>=abs(observed) for v in null)/len(null)
        return dict(verified_lookups=n,positive_primary=dist,positive_hits=sums,
                    token_check='187 in all normal arms' if all(choices[msg]['usage']['prompt_tokens']==187 for row in cards
                    for a in row['arms'].values() for msg in [a['prompts']['normal']]) else 'varies',
                    family_signed_differences_sorted=sorted(fam.values()),paired_family_flip_p_two_sided=p,
                    mean_return_bytes={k:sum(v)/len(v) for k,v in lengths.items()})


if __name__=='__main__':
    out=dict(dp_exhaustive_checks=self_test(),prefix=prefix(),actions=actions(),demo=released_strings(),overlap=query_overlap(), sql=verify_actions())
    f=D/'audit-readers.json';f.write_text(json.dumps(out,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print('Audit completed:',h(f));print(json.dumps(out,ensure_ascii=True))
