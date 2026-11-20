import shutil
from common import *
def main():
    d=read('clean/reader_inputs.json.gz');old=read('clean/reader_inputs.json.gz');mapping={}
    ids=sorted(d)
    for m in ('claude','codex'):
        order=sorted(ids,key=lambda i:sha('shuffle-v4|'+m+'|'+i))
        mapping[m]={i:order[(j+1)%len(order)] for j,i in enumerate(order)}
        for i in ids:d[i]['options'][m]['witness']=old[mapping[m][i]]['options'][m]['witness']
        assert all(i!=x for i,x in mapping[m].items())
        assert sorted(len(d[i]['options'][m]['witness']) for i in ids)==sorted(len(old[i]['options'][m]['witness']) for i in ids)
    for f in ('reader.py','common.py'):shutil.copy2(ROOT/f,ROOT/'shuffle'/f)
    write('shuffle/reader_inputs.json.gz',d);write('shuffle/donors.json',mapping)
    jobs=[{'issue':i,'arm':'witness','reverse':b} for i in ids for b in (False,True)]
    jobs.sort(key=lambda j:sha('schedule4-shuffle|'+canon(j)))
    write('shuffle/schedule.json',jobs)
    files=['reader.py','common.py','reader_inputs.json.gz','schedule.json','donors.json']
    write('shuffle/input_lock.json',{f:sha((ROOT/'shuffle'/f).read_bytes()) for f in files})
    print(len(jobs),'control assignments locked')
if __name__=='__main__':main()
