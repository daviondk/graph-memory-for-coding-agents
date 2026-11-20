"""Score frozen token comparisons and held-forward E2/E3 outcomes."""
import csv
import gzip
import hashlib
import json
from collections import Counter,defaultdict
from statistics import mean
from score import ROOT,ci,readgz
from predict import author
def check(file):
    l=json.loads((ROOT/file).read_text())
    for n,h in l['sha256'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
def save(n,x):(ROOT/n).write_text(json.dumps(x,ensure_ascii=False,indent=1),encoding='utf8')
def csvsave(n,rows):
    with (ROOT/n).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def make_future():
    targets={};coverage=Counter()
    for r in readgz('histories.jsonl.gz'):
        h=r['H'];k=(3*len(h))//4
        prefix=author.atoms_in_text(json.dumps(h[:k],ensure_ascii=False)[:400000])
        pre={(t,v) for t,vs in prefix.items() for v in vs}
        calls=[]
        for msg in h[k:]:
            if msg.get('role')=='assistant':
                calls.extend(c['function']['arguments'] for c in (msg.get('tool_calls') or []) if isinstance(c,dict) and isinstance(c.get('function'),dict) and c['function'].get('arguments'))
        reused=set()
        for arg in calls[:5]:
            a=author.atoms_in_text(arg if isinstance(arg,str) else json.dumps(arg,ensure_ascii=False))
            reused.update((t,v) for t,vs in a.items() for v in vs)
        saved=pre&reused
        reason='eligible' if saved else ('no_future_call' if not calls else 'no_typed_overlap')
        coverage[reason]+=1
        targets[r['i']]=sorted(saved)
    return targets,coverage
def do_token():
    check('token_lock.json')
    target,coverage=make_future();save('future_ground_truth.json',target)
    labels=list(readgz('gold.jsonl.gz'))
    rows=[];kinds=defaultdict(Counter)
    for p in readgz('token_predictions.jsonl.gz'):
        i=p['i'];t=([(a['kind'],a['value']) for a in labels[i]['atoms']] if p['endpoint']=='official' else target[i])
        found=set(map(tuple,p['items']));s=p['S']
        hits=sum(v in s for k,v in t);typed=sum(pair in found for pair in t)
        for a in t:
            kinds[p['endpoint'],p['cost'],p['arm'],a[0]].update({'n':1,'literal':int(a[1] in s),'typed':int(a in found)})
        assert p['used']<=p['cap']
        rows.append({'endpoint':p['endpoint'],'cost':p['cost'],'arm':p['arm'],'i':i,'session':labels[i]['sess'],'client':labels[i]['client'],'n':len(t),'hits':hits,'typed':typed,'chars':len(s),'bytes':p['bytes'],'tokens':p['tokens'],'items':len(found),'cap':p['cap']})
    csvsave('token_casewise.csv',rows)
    summary={}
    for key in sorted({(r['endpoint'],r['cost']) for r in rows}):
        sub=[r for r in rows if (r['endpoint'],r['cost'])==key]
        base={r['i']:r for r in sub if r['arm']=='author_index'}
        aa={}
        for arm in sorted({r['arm'] for r in sub}):
            all_rows=[r for r in sub if r['arm']==arm]
            rs=[r for r in all_rows if r['n']]
            if not rs:continue
            ds=[(r['hits']-base[r['i']]['hits'])/r['n'] for r in rs]
            groups=defaultdict(list)
            for r,d in zip(rs,ds):groups[r['session']].append(d)
            aa[arm]={'n':len(rs),'all_records':len(all_rows),'atoms':sum(r['n'] for r in rs),'macro':mean(r['hits']/r['n'] for r in rs),'micro':sum(r['hits'] for r in rs)/sum(r['n'] for r in rs),'macro_zero_on_no_target':sum(r['hits']/r['n'] for r in rs)/len(all_rows),'typed_macro':mean(r['typed']/r['n'] for r in rs),'delta':mean(ds),'wins':sum(d>0 for d in ds),'losses':sum(d<0 for d in ds),'ties':ds.count(0),'session_ci95':ci(groups) if arm in ['author_fill_grouped','round_robin','witness_grouped'] else None,
                     'mean_tokens_all':mean(r['tokens'] for r in all_rows),'mean_bytes_all':mean(r['bytes'] for r in all_rows),'mean_chars_all':mean(r['chars'] for r in all_rows)}
        summary['|'.join(key)]=aa
    save('token_results.json',{'coverage':coverage,'summaries':summary,'kinds':{'|'.join(k):v for k,v in kinds.items()}})
    print('coverage',coverage)
    for key,rs in summary.items():print(key,{k:round(v['macro']*100,2) for k,v in rs.items()})
def do_e3():
    check('e3_lock.json')
    labels={(g['i'],g['j']):g for g in readgz('e3_labels.jsonl.gz')}
    e2_ids={g['sess'] for g in readgz('gold.jsonl.gz')}
    rows=[]
    for p in readgz('e3_predictions.jsonl.gz'):
        g=labels[p['i'],p['j']]
        pairs=[(k,v) for k,vs in g['atomsF'].items() for v in vs]
        rows.append({k:p[k] for k in ('i','j','arm','used','base','available')}|{'sess':g['sess'],'client':g['client'],'k':g['k'],'n':len(pairs),'hits':sum(v in p['S'] for _,v in pairs),'overlap_e2':g['sess'] in e2_ids})
    csvsave('e3_casewise.csv',rows)
    summary={}
    for name,sub in [('all',rows),('later',[r for r in rows if r['j']>0]),('eligible_later',[r for r in rows if r['j']>0 and r['available']>0]),('first',[r for r in rows if r['j']==0]),('later_non_e2',[r for r in rows if r['j']>0 and not r['overlap_e2']])]:
        base={(r['i'],r['j']):r for r in sub if r['arm']=='production'};stats={}
        for a in sorted({r['arm'] for r in sub}):
            complete=[r for r in sub if r['arm']==a];rs=[r for r in complete if r['n']]
            if not rs: continue
            ds=[(r['hits']-base[r['i'],r['j']]['hits'])/r['n'] for r in rs];groups=defaultdict(list);grp=defaultdict(list)
            for r,d in zip(rs,ds):groups[r['i']].append(d);grp[r['i']].append(r['hits']/r['n'])
            stats[a]={'n_boundaries':len(complete),'defined':len(rs),'defined_chains':len(grp),'atoms':sum(r['n'] for r in rs),'macro_boundary':mean(r['hits']/r['n'] for r in rs),'macro_chain':mean(mean(x) for x in grp.values()),'micro':sum(r['hits'] for r in rs)/sum(r['n'] for r in rs),'delta_vs_production':mean(ds),'wins':sum(d>0 for d in ds),'ties':ds.count(0),'losses':sum(d<0 for d in ds),'chain_ci95':ci(groups) if a in ['sidecar_fixed','sidecar_extra'] else None,'sum_tokens':sum(r['used'] for r in complete)}
        summary[name]=stats
    ids={g['sess'] for g in labels.values()}
    save('e3_results.json',{'n_chains':len(set(i for i,j in labels)),'boundary_total':len(labels),'e2_session_id_overlap':len(ids&e2_ids),'summaries':summary})
    print('e3 overlap',len(ids&e2_ids));print('later',summary['later'])
if __name__=='__main__':
    import sys
    {'token':do_token,'e3':do_e3}[sys.argv[1]]()

