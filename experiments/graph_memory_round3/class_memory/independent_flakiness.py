"""Exploratory reruns of the one item whose per-test count differed between scorers."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from independent_audit import execute, get, write
from independent_sensitivity import alternate_executor,check_design
from independent_sealed import base_payload,clean_reply,load_seals


def main():
    load_seals();check_design();expanded=alternate_executor()
    target='ClassEval_22/get_all_major'
    assignment=next(r for r in get('assignment.json') if r['id']==target)
    item,name=target.split('/')
    r=next(c for c in get('ClassEval_data.json') if c['task_id']==item)
    m=next(x for x in r['methods_info'] if x['method_name']==name)
    blob=base_payload(r,name,m['test_class'],m['test_code'])
    rounds=40
    jobs=[]
    for arm in ['none','graph']:
        key=assignment['arms'][arm]
        text=clean_reply(get('calls/'+key+'.json.gz'))
        if arm=='none':assert 'set()' in text and 'list(majors)' in text
        for j in range(rounds):
            for env,scorer in (('primary',execute),('extended',expanded)):
                jobs.append((arm,env,scorer,dict(blob,grade='generated',candidate=text)))
    def run(job):
        arm,env,fn,payload=job
        result=fn(payload)
        return f'{arm}/{env}', int(result['passed'])
    totals={}
    with ThreadPoolExecutor(3) as pool:
        for key,count in pool.map(run,jobs):
            totals.setdefault(key,Counter())[str(count)]+=1
    write('independent_flakiness.json',{'case':target,'reruns_per_condition':rounds,'test_pass_count_distributions':totals,
          'exploratory':True,'baseline_shared_by_all_nonempty_arms':len({k for a,k in assignment['arms'].items() if a!='none'})==1,
          'reason':'No-memory response converts a set of strings to a list; author tests compare a list in specified order. Each call starts a CPython process with randomized hash order.'})


if __name__=='__main__':main()

