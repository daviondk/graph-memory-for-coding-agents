"""Apply the original evaluator and compare old-side Git patch locations using two parsers."""
import collections
import json
import math
from pathlib import Path
import sys
from statistics import mean

from pyarrow import parquet
from unidiff import PatchSet
from study import ROOT, INPUT, SELECTION, WORK, read, put, sha, lock, ARMS
from patch_diagnostic import original_lines, unidiff_old, intervals
OFFICIAL=Path('D:/CodexResearch/x20-round15-external-scoring')
sys.path.insert(0,str(OFFICIAL))
from swe_eval import ExploreEvaluator

def discordant(rows,a,b,key):
    win=sum(r['outcomes'][a][key] and not r['outcomes'][b][key] for r in rows)
    loss=sum(r['outcomes'][b][key] and not r['outcomes'][a][key] for r in rows)
    informative=win+loss
    p=min(1,2*sum(math.comb(informative,v) for v in range(min(win,loss)+1))/2**informative) if informative else 1.0
    return dict(wins=win,losses=loss,ties=len(rows)-informative,exact_p=p)

def main():
    lock(ROOT/'read.lock.json')
    import itertools
    actions=read(ROOT/'actions.json.gz')
    menus=read(ROOT/'menus.json.gz')
    priors={(x['instance_id'],x['source']):x for x in read(INPUT/'input-priors.json.gz')}
    allids={i for i,_ in priors};assert len(allids)==54
    labels={}
    python_insertions={}
    verified=WORK/'graph_memory_round3/real_swe/official_verified.parquet'
    assert sha(verified.read_bytes())==read(ROOT/'source.lock.json')['verified_sha']
    for r in parquet.read_table(verified,columns=['instance_id','patch']).to_pylist():
        if r['instance_id'] not in allids:continue
        p=r['patch'];labels[r['instance_id']]=original_lines(p)
        assert labels[r['instance_id']]==unidiff_old(p)
        python_insertions[r['instance_id']]=sum(line.is_added for f in PatchSet(p.splitlines(keepends=True)) if f.target_file.endswith('.py') for h in f for line in h)
    inv=read(WORK/'graph_memory_round15/external_scoring/native-source.json')
    assert sha((OFFICIAL/'swe_eval.py').read_bytes())==inv['swe_eval.py']['sha256']
    b=OFFICIAL/'swe-explore.jsonl'
    assert sha(b.read_bytes())==read(INPUT/'cohort.json')['sha_external']
    ev=ExploreEvaluator(b)
    ids=sorted(x['id'] for x in menus)
    point=collections.defaultdict(dict)
    for a in actions:point[a['solver']+'/'+a['arm']][a['id']]=a
    native={k:ev.evaluate(lambda q,i:point[k][i]['region'],ids,['precision','recall','f1_score']) for k in point}
    rows=[]
    for row in menus:
        i=row['id'];mark=labels[i];q=priors[i,row['source']]
        shown={(v['path'],j) for v in q['views3'] for j,_ in v['lines']}
        out={}
        for arm in ARMS:
            menu=row['menus'][arm];candidate=set().union(*(intervals([[x['p'],x['s'],x['e']]]) for x in menu.values()))
            assert len(candidate)==60 and candidate<=shown
            for solver in ('qwen','lexical'):
                k=solver+'/'+arm;a=point[k][i];opened=intervals(a['region'])
                assert opened<=candidate and len(opened)<=12
                out[k]={**native[k][i],'patch_read_hit':bool(mark & opened),'patch_menu_hit':bool(mark & candidate),
                        'read_lines':len(opened),'menu_blocks':len(menu),'available':bool(opened),'choice':a['choice']}
        rows.append({'id':i,'repo':row['repo'],'source':row['source'],'old_lines':len(mark),'insertions':python_insertions[i],
                     'visible_old_lines':len(shown&mark),'primary_menu_discordance':row['menus']['scope24']!=row['menus']['lexical24'],'outcomes':out})
    agg={}
    for k in point:
        agg[k]={v:sum(int(r['outcomes'][k][v]) for r in rows) for v in ('patch_read_hit','patch_menu_hit','available','read_lines','menu_blocks')}
        agg[k].update({m:mean(r['outcomes'][k][m] for r in rows) for m in ('precision','recall','f1_score')})
    full_reach=set()
    for (i,src),r in priors.items():
        if {(v['path'],j) for v in r['views3'] for j,_ in v['lines']}&labels[i]:full_reach.add(i)
    primary=[r for r in rows if r['primary_menu_discordance']]
    contrasts={}
    for a,bx in [('qwen/scope24','qwen/lexical24'),('qwen/scope24','qwen/recent'),('qwen/scope24','lexical/scope24'),('qwen/lexical24','lexical/lexical24'),('qwen/recent','lexical/recent')]:
        tag=a+' - '+bx
        contrasts[tag]={c:discordant(batch,a,bx,'patch_read_hit') for c,batch in [('all',rows),('with_old',[r for r in rows if r['old_lines']]),('primary_discordant',primary)]}
    raw=[json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines()]
    costs={'model_calls':len(raw),'prompt_tokens':sum(x['usage']['prompt_tokens'] for x in raw),'completion_tokens':sum(x['usage']['completion_tokens'] for x in raw),'seconds':sum(x['elapsed'] for x in raw),
           'physical_bytes_by_solver':{s:sum(a.get('bytes_read',0) for a in actions if a['solver']==s) for s in ('qwen','lexical')}}
    census={'full_tasks':len(allids),'full_with_old':sum(bool(v) for v in labels.values()),'full_pure_python_insertion':sum(not labels[i] and python_insertions[i]>0 for i in labels),'full_reachable_any_source':len(full_reach),
            'selected':len(rows),'selected_with_old':sum(bool(r['old_lines']) for r in rows),'selected_visible_old':sum(bool(r['visible_old_lines']) for r in rows),
            'selected_pure_python_insertion':sum(not r['old_lines'] and r['insertions']>0 for r in rows)}

    put('evaluation.json.gz',rows)
    put('results.json',dict(arms=agg,contrasts=contrasts,coverage=census,costs=costs))
    print(census,costs,agg,flush=True)
if __name__=='__main__':main()
