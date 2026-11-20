from concurrent.futures import ThreadPoolExecutor
from common import *
from runner import execute

def evaluate(task):
    r, dataset=task;i=r['id']; sig=r['interface']; entry=sig.split('(')[0];cache={}; rows={}
    for label,src in [('reference',dataset['code']),('stub','def '+sig+':\n    raise NotImplementedError\n')]:
        d=ROOT/'grading'/str(i);d.mkdir(exist_ok=True,parents=True);(d/(label+'.py')).write_bytes(src.encode())
    for branch in ('reference','stub','current','raw','note'):
        p=ROOT/'grading'/str(i)/(branch+'.py') if branch in ('reference','stub') else ROOT/path(i,branch+'.py')
        key=sha(p.read_bytes())
        if key not in cache:cache[key]=execute(p,entry,dataset['test_imports'],dataset['test_list'])
        rows[branch]=dict(code_sha=key,**cache[key])
    return i,rows
def main():
    check(read('design_lock.json')['hashes']);check(read('prediction_lock.json')['hashes'])
    dataset={r['task_id']:r for r in read('upstream-sanitized-mbpp.json')};items=read('roster.json')['items']
    with ThreadPoolExecutor(max_workers=3) as pool:results=dict(pool.map(evaluate,[(r,dataset[r['id']]) for r in items]))
    save('scores.json',results)
    print(stamp(),'scored',len(results),flush=True)
if __name__=='__main__':main()

