"""Paired bounded-preimage metrics; all predictors are fixed before this module reads gold."""
import csv,gzip,hashlib,json,math,random,statistics,sys
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parent
ARMS=['drop_recenthead','drop_recenttail','drop_mid','drop_lexical','drop_fused','rebase_recenthead','rebase_mid','rebase_fused','stale_fused','one_reopen','paths']
def read(p):return json.loads(p.read_bytes())
def rows(base):
    for fn in sorted((base/'scores').glob('*.jsonl.gz')):
        with gzip.open(fn,'rt',encoding='utf8') as f:
            for l in f:yield json.loads(l)
def stats(rs):
    return {str(b):{a:{'preimage':sum(r['metrics'][f'{a}:{b}'][1] for r in rs),'path':sum(r['metrics'][f'{a}:{b}'][0] for r in rs),'tokens':sum(r['metrics'][f'{a}:{b}'][2] for r in rs)} for a in ARMS} for b in (256,512,1024)}
def contrast(rs,a,b,budget=512):
    ds=defaultdict(lambda:[0,0]);wins=0;losses=0
    for r in rs:
        d=r['metrics'][f'{a}:{budget}'][1]-r['metrics'][f'{b}:{budget}'][1]
        ds[r['instance']][0]+=d;ds[r['instance']][1]+=1;wins+=d>0;losses+=d<0
    if not ds:return {}
    units=list(ds.values());rng=random.Random(41711);ests=[]
    for _ in range(5000):
        sample=rng.choices(units,k=len(units));ests.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
    ests.sort()
    return {'opportunities':len(rs),'issues':len(ds),'W':wins,'L':losses,'T':len(rs)-wins-losses,'difference':(wins-losses)/len(rs),'issue_cluster_95':[ests[124],ests[4874]]}
def group(rs):
    accepted=[r for r in rs if r['accepted']]
    halves={str(k):[r for r in accepted if int(hashlib.sha256(('split4|'+r['instance']).encode()).hexdigest(),16)%2==k] for k in (0,1)}
    return {'all_intents':len(rs),'accepted':len(accepted),'unique_issues':len({r['instance'] for r in accepted}),'models':dict(Counter(r['model'] for r in accepted)),'stats_accepted':stats(accepted),'stats_all_intents':stats(rs),
       'ceilings':{mode:sum(r['ceiling'][mode] for r in accepted) for mode in ('drop','rebase','stale')},
       'known_whole':sum(r['known_whole_at_boundary'] for r in accepted),'whole_unique':sum(r['whole_hit'] for r in accepted),
       'primary_rebase_fused_minus_drop_fused':contrast(accepted,'rebase_fused','drop_fused'),
       'primary_rebase_fused_minus_recenthead':contrast(accepted,'rebase_fused','drop_recenthead'),
       'controls':{a+'-drop_mid':contrast(accepted,a,'drop_mid') for a in ('drop_recenthead','drop_recenttail','drop_lexical','drop_fused','rebase_mid','one_reopen')},
       'update_on_previously_edited':contrast([r for r in accepted if r['edited_before']],'rebase_fused','drop_fused'),
       'disjoint_halves':{k:contrast(v,'rebase_fused','drop_fused') for k,v in halves.items()},
       'uncontaminated_full':{'n':sum(r['whole_hit'] and not r['opaque_since'] for r in accepted),'stats':stats([r for r in accepted if r['whole_hit'] and not r['opaque_since']])}}
def main():
    native=list(rows(ROOT));tagged=list(rows(ROOT/'tagged')); cohorts={'native':native,'tagged':tagged};out={k:group(v) for k,v in cohorts.items()}
    a={(r['instance'],r['traj']) for r in native};b={(r['instance'],r['traj']) for r in tagged};same={r['instance'] for r in native}&{r['instance'] for r in tagged}
    out['identity']={'session_overlap':len(a&b),'issue_overlap':len(same),'native_sessions':len(a),'tagged_sessions':len(b)}
    out['all']=group(native+tagged)
    (ROOT/'results.json').write_text(json.dumps(out,indent=1))
    with (ROOT/'per_issue.csv').open('w',newline='',encoding='utf8') as f:
        cols=['cohort','issue','n',*ARMS];writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for cohort,rs in cohorts.items():
            groups=defaultdict(list)
            for r in rs:
                if r['accepted']:groups[r['instance']].append(r)
            for inst,rr in sorted(groups.items()):writer.writerow({'cohort':cohort,'issue':inst,'n':len(rr),**{a:sum(r['metrics'][a+':512'][1] for r in rr) for a in ARMS}})
    print({k:{'n':v['accepted'],'primary':v['primary_rebase_fused_minus_drop_fused'],'counts':{a:x['preimage'] for a,x in v['stats_accepted']['512'].items()}} for k,v in out.items() if k!='identity'})
if __name__=='__main__':main()
