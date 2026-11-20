"""Independent consistency checks on published run logs and outcome tables. Standard library."""
import csv, gzip, hashlib, json, math, statistics, zipfile
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[1]
def js(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    verify={}
    for key,val in js('global_freeze.json')['sha256'].items():assert sha(ROOT/key)==val
    assert sha(ROOT/'field/sample.json')==js('field/sample_freeze.json')['sha256']
    field=[json.loads(l) for l in (ROOT/'field/traces.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(field)==48 and len({r['path'] for r in field})==48
    assert not set(r['repo'] for r in field)&set(js('field/excluded_repos.json'))
    assert js('field/summary.json')['total']['with_limit']==sum(any(e['parse']['limits'] for e in r['events']) for r in field)
    verify['field_traces']=len(field)
    frozen=[]
    for study in ['search','search_replication']:
        data=list(csv.DictReader((ROOT/study/'observations.csv').open(encoding='utf-8-sig')))
        totals=Counter()
        assert len(data)==36
        for r in data:
            raw=js(study+'/runs/'+r['id']+'.json')
            assert hashlib.sha256(raw['prompt'].encode()).hexdigest()==raw['prompt_sha256']
            events=js(study+'/executed_actions.json')
            action=next(e for e in events if e['id']==r['id'])
            target=r['target'].replace('\\','/')+':'+r['target_line']+':'
            win=any(l.replace('\\','/').removeprefix('./').startswith(target) for l in action['stdout'])
            assert int(win)==int(r['pass'])
            if raw['status']=='ok':assert json.loads(raw['text']).get('choice')==r['choice']
            totals[r['arm']]+=win
        assert all(totals[k]==v['pass_count'] for k,v in js(study+'/results.json')['arms'].items())
        verify[study]=dict(totals)
        frozen.append({r['id']:js(study+'/runs/'+r['id']+'.json')['prompt_sha256'] for r in data})
    assert frozen[0]==frozen[1]
    scores=js('probe/scores.json');assert len(scores)==36
    totals=Counter()
    for row in scores:
        pred=row['submitted']; ok=isinstance(pred,list) and len(pred)==4 and all(type(x) is type(y) and x==y for x,y in zip(pred,row['expected']))
        assert ok==row['perfect']
        totals[row['arm']]+=ok
    assert all(js('probe/summary.json')['counts'][k]['perfect']==v for k,v in totals.items())
    verify['probe']=dict(totals)
    total_real=Counter()
    real_rows=js('probe_real/scores.json')
    assert len(real_rows)==12
    for r in real_rows:
        assert r['expected']==r['predictions'] if r['perfect'] else r['expected']!=r['predictions']
        total_real[r['arm']]+=r['expected']==r['predictions']
    assert all(js('probe_real/summary.json')['arms'][k]['perfect']==v for k,v in total_real.items())
    verify['probe_real']=dict(total_real)
    sub=ROOT/'retention/results';counts=defaultdict(lambda:[0,0,0,0,0])
    with gzip.open(sub/'steps.csv.gz','rt',encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            query,cache,missing,answer=(int(r[k],16) for k in ['query_mask','cache_mask','missing_mask','answer_mask'])
            assert query & ~cache == missing
            n=missing.bit_count() if r['tool']=='field' else len({i//4 for i in range(32) if missing&(1<<i)})
            assert n==int(r['required_reads'])
            assert min(n,2)==int(r['actual_reads']) and (answer==query)==bool(int(r['correct']))
            t=counts[(r['seed'],r['rho'],r['tool'],r['policy'])]
            for i,value in enumerate([1,n,min(n,2),int(r['correct']),int(r['returned_values'])]):t[i]+=value
    with (sub/'worlds.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            vals=counts[r['seed'],r['rho'],r['tool'],r['policy']]
            assert vals[0]==int(r['jobs'])
            for i,k in enumerate(['required_reads','actual_reads','correct','returned_values'],start=1):
                # worlds.csv stores sums; accept means only if table is normalized.
                assert math.isclose(vals[i],float(r[k]),abs_tol=1e-7) or math.isclose(vals[i]/vals[0],float(r[k]),abs_tol=1e-7)
    verify['simulated_rows']=sum(v[0] for v in counts.values())
    print(json.dumps(verify,indent=2))
if __name__=='__main__':main()

