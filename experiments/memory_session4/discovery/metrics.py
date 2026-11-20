"""Paired success is correct next target UID. All identifiable positive targets count, including absences."""
import csv,gzip,hashlib,json,random
from collections import Counter,defaultdict
from pathlib import Path
from fetch import ROOT,SPLITS
from memory import load_rows,TARGETS
PAIRS=[('focus_cal','last_cal'),('focus_cal','released'),('focus_on_tagged','last_cal_tagged'),('persistent_cal','focus_cal'),('last_cal','released'),('last_click_editable','released'),('last_cal_tagged','released'),('focus_always','last_click_editable'),('lexical','released')]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def score(verify=False):
    for n in ('input_lock.json','output_lock.json'):
        k=json.loads((ROOT/n).read_bytes())['files'];assert all(digest(ROOT/f)==h for f,h in k.items())
    groups=defaultdict(lambda:defaultdict(list));rosters=Counter();original=Counter();allrows=[];kinds=defaultdict(Counter)
    with gzip.open(ROOT/'predictions.jsonl.gz','rt',encoding='utf8') as f:
        for s in SPLITS[1:]:
            for d,rows in load_rows(s).items():
                for r in rows:
                    p=json.loads(next(f));assert (s,d,r['turn'])==(p['s'],p['d'],p['i'])
                    for j in ('last_from','focus_from'):assert p[j] is None or p[j]<r['turn']
                    assert all(v is None or any(v==u for u,t,b in r['c']) for v in p['pred'].values())
                    original[s,'all']+=1
                    if r['k'] not in TARGETS:continue
                    original[s,'target_actions']+=1
                    if not r['y']:continue
                    correct={a:int(y==r['y']) for a,y in p['pred'].items()};present=any(r['y']==v[0] for v in r['c'])
                    correct.update({'N':1,'pool':int(present)})
                    groups[s][d].append(correct);groups['pooled'][d].append(correct)
                    for a,b in PAIRS:
                        k='|'.join((a,b));correct[k]=correct[a]-correct[b]
                        correct['wins|'+k]=int(correct[k]>0);correct['loss|'+k]=int(correct[k]<0)
                    allrows.append({'split':s,'demo':d,'turn':r['turn'],'kind':r['k'],'target':r['y'],'in_pool':int(present),**p['pred']})
                    for g in (s,'pooled'):
                        kinds[(g,r['k'])].update(correct)
        assert not f.readline()
    result={}; per_demo=[]
    for s,ds in groups.items():
        summaries=[]
        for d,rows in ds.items():
            vals=Counter()
            for row in rows:vals.update(row)
            summaries.append(vals)
            if s!='pooled':per_demo.append({'split':s,'demo':d,**dict(vals)})
        total=Counter()
        for v in summaries:total.update(v)
        contrasts={}
        for a,b in PAIRS:
            k='|'.join((a,b));pairs=[(v[k],v['N']) for v in summaries];rng=random.Random(17112026)
            est=[]
            for _ in range(2000):
                draw=rng.choices(pairs,k=len(pairs));est.append(sum(x[0] for x in draw)/sum(x[1] for x in draw))
            est.sort()
            contrasts[k]={'delta':total[k]/total['N'],'win':total['wins|'+k],'loss':total['loss|'+k],
                          'ties':total['N']-total['wins|'+k]-total['loss|'+k],'ci95':[est[49],est[1949]]}
        result[s]={'all_turns':sum(original[q,'all'] for q in SPLITS[1:]) if s=='pooled' else original[s,'all'],
            'all_element_actions_including_unidentified':sum(original[q,'target_actions'] for q in SPLITS[1:]) if s=='pooled' else original[s,'target_actions'],
            'identified':total['N'],'demos':len(ds),'retrieval_pool_covers':total['pool'],'correct':{k:total[k] for k in allrows[0] if k not in ('split','demo','turn','kind','target','in_pool')},'contrasts':contrasts}
    names=list(result['pooled']['correct'])
    result['mean_unweighted_split_accuracy']={a:sum(result[s]['correct'][a]/result[s]['identified'] for s in SPLITS[1:])/5 for a in names}
    result['intent_groups']={s+'/'+k:{a:c[a] for a in names+['N','pool']} for (s,k),c in kinds.items()}
    if verify:
        assert result==json.loads((ROOT/'results.json').read_bytes())
        for name,rows in [('per_demo.csv',per_demo),('per_action.csv',allrows)]:
            with (ROOT/name).open(encoding='utf8',newline='') as f:assert list(csv.DictReader(f))==[{k:'' if v is None else str(v) for k,v in row.items()} for row in rows]
    else:
        for name,rows in [('per_demo.csv',per_demo),('per_action.csv',allrows)]:
            with (ROOT/name).open('w',encoding='utf8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        (ROOT/'results.json').write_text(json.dumps(result,indent=1))
    print(json.dumps({k:result['pooled'][k] for k in ('identified','demos','retrieval_pool_covers','correct')},indent=1))
    print(result['pooled']['contrasts']['focus_cal|last_cal'])
if __name__=='__main__':
    import sys
    score('--verify' in sys.argv)

