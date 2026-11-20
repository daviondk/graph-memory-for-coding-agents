from concurrent.futures import ThreadPoolExecutor
from common import *
def run(d):
    f=read('fixtures/'+d['name']+'.json')
    path='grades/'+d['name']+'-'+sha(d['candidate'])+'.json'
    if (ROOT/path).is_file():return
    outcomes=grade(d['name'],d['candidate'],f['cases'])
    save(path,outcomes)
def main():
    files=read('output_lock.json')['files']; assert freeze(files)==files
    ds=read('decisions.json')
    dedup={(d['name'],sha(d['candidate'])):d for d in ds}
    with ThreadPoolExecutor(2) as ex:list(ex.map(run,dedup.values()))
    print('graded',len(dedup),'distinct module versions across',len(ds),'assignments')
if __name__=='__main__':main()

