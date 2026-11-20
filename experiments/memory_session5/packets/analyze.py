"""Calculate paired effects with corpus-level resampling units and explicit costs."""
import json,math,random,statistics
from collections import defaultdict,Counter
from common import ROOT,rows
from policy import BUDGETS,ARMS
def interval(sample,a,base,level,b):
    group=defaultdict(lambda:[0,0]);w=l=0
    for r in sample:
        diff=r['metrics'][b][a][0]-r['metrics'][b][base][0]
        v=group[r[level]];v[0]+=diff;v[1]+=1;w+=diff>0;l+=diff<0
    units=sorted(group);rng=random.Random(117052026);ds=[];pairs=[group[x] for x in units]
    for j in range(4000):
        s=rng.choices(pairs,k=len(units));ds.append(sum(x[0] for x in s)/sum(x[1] for x in s))
    ds.sort()
    return {'units':len(units),'n':len(sample),'wins':w,'losses':l,'difference':(w-l)/len(sample),'ci95':[ds[100],ds[3899]]}
def summary(rs,b):
    return {a:{'hit':sum(r['metrics'][b][a][0] for r in rs),'average_tokens':sum(r['metrics'][b][a][1] for r in rs)/len(rs)} for a in ARMS}
def main():
    allrows=[r for k in range(8) for r in rows(ROOT/'metrics'/f'{k}.jsonl.gz')];rs=[r for r in allrows if r['accepted']]
    result={};corpora={}
    for split in ['train','test']:
        sets=[(r['instance'],r['traj'],r['model'],r['format'],len(r['events'])) for k in range(8) for r in rows(ROOT/'source'/split/f'{k}.jsonl.gz')]
        corpora[split]={'tasks':len(sets),'repositories':sorted({i.split('.')[0] for i,*_ in sets}),'events':sum(r[-1] for r in sets),'models':dict(Counter(r[2] for r in sets)),'formats':dict(Counter(r[3] for r in sets))}
    for budget in BUDGETS:
        b=str(budget);comparisons={}
        for control in ['reset_tail','rebased_tail','rebased_center','latest_contiguous','first_page','marginal']:
            comparisons[control]={level:interval(rs,'joint',control,level,b) for level in ['repo','id']}
        result[b]={'n':len(rs),'metrics':summary(rs,b),'all_intents':summary(allrows,b),'paired_joint_minus':comparisons,
                  'by_repository':{repo:{'n':len(rr),'hits':{a:v['hit'] for a,v in summary(rr,b).items()}} for repo in sorted({r['repo'] for r in rs}) if(rr:=[r for r in rs if r['repo']==repo])},
                  'by_format':{fmt:{'n':len(rr),'hits':{a:v['hit'] for a,v in summary(rr,b).items()}} for fmt in ['native','tagged'] if(rr:=[r for r in rs if r['format']==fmt])}}
    out={'corpora':corpora,'test_tasks_with_accepted':len({r['id'] for r in rs}),'new_train_test_repo_overlap':sorted(set(corpora['train']['repositories'])&set(corpora['test']['repositories'])),'results':result}
    (ROOT/'results.json').write_text(json.dumps(out,ensure_ascii=True,indent=1))
    for b,vals in result.items():print(b,vals['n'],{k:v['hit'] for k,v in vals['metrics'].items()},vals['paired_joint_minus']['rebased_tail']['repo'])
if __name__=='__main__':main()
