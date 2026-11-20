from pathlib import Path
import concurrent.futures,subprocess,json,sys
ROOT=Path(__file__).resolve().parent
def get(item):
    repo,meta=item;p=ROOT.parent/'mirrors'/repo.replace('/','__');boundary=meta['commits'][0]
    subprocess.run(['git','-C',str(p),'fetch','--depth=100','origin',boundary],capture_output=True,timeout=120,check=True)
    revs=subprocess.check_output(['git','-C',str(p),'rev-list','--max-count=43','--first-parent',boundary]).decode().splitlines()[::-1]
    assert len(revs)==43 and len(set(revs)&set(meta['commits']))==1
    return repo,revs
if __name__=='__main__':
    old=json.loads((ROOT.parent/'source_lock.json').read_bytes());eligible=json.loads((ROOT.parent/'real_intents.json').read_bytes())['queries']
    with concurrent.futures.ThreadPoolExecutor(4) as pool:o=dict(pool.map(get,[(r,old[r]) for r in sorted(eligible)]))
    (ROOT/'source_lock.json').write_text(json.dumps(o,indent=1));print(len(o),'series')
