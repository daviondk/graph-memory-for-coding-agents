import json
from collections import Counter,defaultdict
from common import ROOT,rows
from analyze import interval
from policy import BUDGETS
T=ROOT/'transfer'
def main():
    selected=json.loads((T/'chosen_control.json').read_bytes());allrows=[r for k in range(8) for r in rows(T/'test/metrics'/f'{k}.jsonl.gz')];rs=[r for r in allrows if r['accepted']]
    old=json.loads((ROOT/'results.json').read_bytes())
    report={'selection':'Training A test uses n=3405 A known outcomes for simple control selection; B test unseen new instances. A posthoc labels only, B prospective.', 'B_repository_count':len(set(r['repo'] for r in rs)), 'B_tasks_with_accepted':len(set(r['id'] for r in rs)), 'B_intents':len(allrows),'results':{}}
    for b in map(str,BUDGETS):
        names=sorted(rs[0]['metrics'][b]);metric={a:{'hit':sum(r['metrics'][b][a][0] for r in rs),'mean_tokens':sum(r['metrics'][b][a][1] for r in rs)/len(rs)} for a in names}
        outcomes={a:interval(rs,'joint',a,'repo',b) for a in names if a!='joint'}
        report['results'][b]={'A_posthoc_comparator_hits':selected[b]['hits'],'A_joint':old['results'][b]['metrics']['joint']['hit'],'validated_simple_control':selected[b]['name'],'B_metrics':metric,'B_joint_contrasts':outcomes,'B_n':len(rs),'B_issue_cluster_primary':interval(rs,'joint',selected[b]['name'],'id',b)}
    (T/'results.json').write_text(json.dumps(report,ensure_ascii=True,indent=1))
    for b,row in report['results'].items():
        query=row['validated_simple_control'];print(b,query,row['A_joint'],row['A_posthoc_comparator_hits'][query],row['B_metrics']['joint'],row['B_metrics'][query],row['B_joint_contrasts'][query],flush=True)
if __name__=='__main__':main()
