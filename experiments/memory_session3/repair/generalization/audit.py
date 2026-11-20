"""Independent offline audit from frozen source hashes, raw observed values and property tests."""
from pathlib import Path
import collections,csv,json,math,random,sys
from generate import ROOT,UP,load,save,sha,canon
from oracle import valid

ARMS=['original','reference','empty','recent','witness','full']
def compute():
    lock=load(ROOT/'lock.json')
    for p,h in lock['sha256'].items():assert sha((ROOT/p).read_bytes())==h
    assert sha((ROOT.parent/'output_lock.json').read_bytes())==lock['solver_output_lock_sha256']
    for f,h in load(ROOT.parent/'output_lock.json')['files'].items():assert sha((ROOT.parent/f).read_bytes())==h
    cases=load(ROOT/'cases.json');bindings=load(ROOT/'assignments.json')
    for d in load(ROOT.parent/'decisions.json'):assert bindings[d['name']][d['arm']]==sha(d['candidate'].encode())
    historical={}
    with (ROOT.parent/'per_program.csv').open(encoding='utf8',newline='') as f:
        for r in csv.DictReader(f):historical[r['program']]=r
    docs=load(ROOT/'generation.json')
    rows=[];errors=collections.Counter();detail=[]
    for name,assign in bindings.items():
        public={canon(json.loads(line)[0]) for line in (UP/'json_testcases'/(name+'.json')).read_text(encoding='utf8').splitlines()}
        excluded=public|{canon(args) for args in docs['filters'][name]['parsed_examples']}
        if name=='hanoi':
            for s in list(excluded):
                args=json.loads(s)
                if len(args)<3:excluded.add(canon(args+([1,3] if len(args)==1 else [3])))
        assert len(cases[name])==len({x['key'] for x in cases[name]})==16
        for c in cases[name]:
            assert canon(c['input']) not in excluded and c['key']==sha(canon(c['input']).encode())
        out={'program':name,'cases':len(cases[name])}
        for arm in ARMS:
            h=assign[arm]
            if arm in ('original','reference'):
                folder='python_programs' if arm=='original' else 'correct_python_programs'
                assert sha((UP/folder/(name+'.py')).read_text(encoding='utf8').encode())==h
            records=load(ROOT/'receipts'/(name+'-'+h+'.json'))
            assert len(records)==len(cases[name])
            passed=0
            for c,rec in zip(cases[name],records):
                assert rec['key']==c['key']
                obs=rec['observation']
                ok=obs['status']=='return' and valid(name,c['input'],obs['value'])
                assert ok==rec['ok'];passed+=int(ok)
                if not ok:
                    errors[arm+'|'+('wrong_value' if obs['status']=='return' else obs['status'])]+=1
                    detail.append({'program':name,'input_id':c['key'],'arm':arm,'receipt':name+'-'+h,'status':obs['status']})
            out[arm]=passed
            if arm!='reference':out['public_future_'+arm]=historical[name]['future_all_'+arm]=='True'
        rows.append(out)
    def compare(group,a,b):
        diff=[int(r[a]==16)-int(r[b]==16) for r in group]
        w,l=diff.count(1),diff.count(-1);n=w+l
        if not diff:return None
        rng=random.Random(17112026);boot=[]
        for _ in range(10000):boot.append(sum(rng.choices(diff,k=len(group)))/len(group))
        boot.sort()
        return {'wins':w,'losses':l,'ties':len(diff)-n,'delta_pp':100*sum(diff)/len(diff),
                'paired_cluster_bootstrap95_pp':[100*boot[249],100*boot[9749]],
                'exact_discordance_two_sided_p':min(1,2*sum(math.comb(n,i) for i in range(min(w,l)+1))/(2**n))}
    def group(rs):
        return {'programs':len(rs),'cases':16*len(rs),'success':{k:sum(r[k]==16 for r in rs) for k in ARMS},
                'passed_inputs':{k:sum(r[k] for r in rs) for k in ARMS},
                'witness_vs':{a:compare(rs,'witness',a) for a in ['recent','empty','full']},
                'new_pass_old_fail':{a:[r['program'] for r in rs if r[a]==16 and not r['public_future_'+a]] for a in ARMS if a!='reference'},
                'old_pass_new_fail':{a:[r['program'] for r in rs if r[a]!=16 and r['public_future_'+a]] for a in ARMS if a!='reference'},
                'both_suites_pass':{a:sum(r[a]==16 and r['public_future_'+a] for r in rs) for a in ARMS if a!='reference'}}
    usable=[r for r in rows if r['reference']==16];sensitive=[r for r in usable if r['original']!=16]
    candidate_hashes={(name,assign[arm]) for name,assign in bindings.items() for arm in ['empty','recent','witness','full']}
    unique={(name,h) for name,assign in bindings.items() for h in assign.values()}
    return rows,detail,{'all_including_reference_failures':group(rows),'primary':group(usable),'sensitive':group(sensitive),
        'reference_exclusions':[r['program'] for r in rows if r['reference']!=16],'undetected_originals':[r['program'] for r in usable if r['original']==16],
        'distinct_candidate_programs':len(candidate_hashes),'distinct_all_programs':len(unique),'error_types':dict(errors)}
def main():
    rows,detail,res=compute()
    if '--check' in sys.argv:
        assert res==load(ROOT/'results.json') and detail==load(ROOT/'failed_cases.json')
        print('Verified',res['distinct_all_programs'],'real modules and',16*res['distinct_all_programs'],'case receipts')
        return
    with (ROOT/'per_program.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    save('results.json',res);save('failed_cases.json',detail)
    print(res['primary'])
if __name__=='__main__':main()
