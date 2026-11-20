from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from common import *
import grade
import plus_grade
def main():
    check(read('prediction_lock.json')['hashes'])
    src={r['task_id']:r for r in read('upstream-sanitized-mbpp.json')}
    enh={int(r['task_id']):r for line in gzip.decompress((ROOT/'mbppplus.jsonl.gz').read_bytes()).splitlines() if (r:=json.loads(line))}
    items=read('roster.json')['items']; report={}
    for ep,filename,func,inps in [('author','scores.json',grade.evaluate,[(r,src[r['id']]) for r in items]),('enhanced','plus_scores.json',plus_grade.grade_plus,[(r,src[r['id']],enh.get(r['id'])) for r in items])]:
        old=read(filename)
        with ThreadPoolExecutor(max_workers=3) as pool: fresh={str(i):d for i,d in pool.map(func,inps)}
        assert set(fresh)==set(old)
        diffs=[]; outcomes=0
        for i in old:
            assert set(fresh[i])==set(old[i])
            for b in old[i]:
                if not isinstance(old[i][b],dict):assert fresh[i][b]==old[i][b];continue
                outcomes+=1
                if fresh[i][b]!=old[i][b]:diffs.append({'id':int(i),'branch':b,'first':old[i][b],'repeat':fresh[i][b]})
        report[ep]=dict(physical_outcome_rows=outcomes,differences=diffs,all_equal=not diffs)
    save('replay.json',report)
    print(canonical(report))
if __name__=='__main__':main()

