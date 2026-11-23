"""Verify exact responses, rendered menus, saved tool actions, and native precision from scratch."""
import json
from pathlib import Path
from study import ROOT, INPUT, WORK, SELECTION, ARMS, read, sha, compact, prompt, lexical, lock, put
from pyarrow import parquet

def main():
    for name in ['design.lock.json','response.lock.json','read.lock.json']:lock(ROOT/name)
    tasks={q['id']:q for q in read(ROOT/'menus.json.gz')};assign=read(ROOT/'assignment.json')
    prompts=read(ROOT/'prompts.json.gz');actions=read(ROOT/'actions.json.gz')
    calls={r['sha']:r for r in (json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines())}
    verify_file=WORK/'graph_memory_round3/real_swe/official_verified.parquet'
    issues={r['instance_id']:r['problem_statement'] for r in parquet.read_table(verify_file,columns=['instance_id','problem_statement']).to_pylist()}
    assert len(assign)==len(tasks)*3 and len(actions)==len(assign)*2
    assert all(sha(p.encode())==h for h,p in prompts.items()) and set(prompts)==set(calls)
    assert all(sha(r['raw'].encode())==r['response_sha'] and json.loads(r['raw'])['usage']==r['usage'] for r in calls.values())
    outcomes={r['id']:r for r in read(ROOT/'evaluation.json.gz')}
    goldfile=Path('D:/CodexResearch/x20-round15-external-scoring/swe-explore.jsonl')
    gt={r['instance_id']:{(q['path'],n) for q in r['ground_truth']['read_core_regions'] for n in range(q['start'],q['end']+1)}
        for r in (json.loads(l) for l in goldfile.read_bytes().splitlines()) if r['instance_id'] in tasks}
    for task in assign:
        iid=task['id'];arm=task['arm'];m=tasks[iid]['menus'][arm]
        assert sha(compact(prompt(issues[iid],m)))==task['sha']
        assert lexical(issues[iid],m)==task['lexical_choice']
    for act in actions:
        r=outcomes[act['id']]['outcomes'][act['solver']+'/'+act['arm']]
        selected={(f,n) for f,s,e in act['region'] for n in range(s,e+1)}
        overlap=len(selected & gt[act['id']])
        precision=overlap/len(selected) if selected else 0
        recall=overlap/len(gt[act['id']]) if gt[act['id']] else 0
        f1=2*precision*recall/(precision+recall) if precision+recall else 0
        assert abs(precision-r['precision'])<1e-12 and abs(recall-r['recall'])<1e-12 and abs(f1-r['f1_score'])<1e-12
        if act['solver']=='qwen': assert act['choice']==calls[act['sha']]['choice']
    print(len(tasks),'issues',len(calls),'native responses',len(assign),'rendered menus',len(actions),'action outcomes verified')

if __name__=='__main__':main()
