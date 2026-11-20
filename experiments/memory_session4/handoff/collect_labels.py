"""Release hidden grades only after both inference prediction sets are frozen."""
from concurrent.futures import ThreadPoolExecutor
from common import *
from fetch import validated

def get_one(item):
    key,o=item;m,i,_=key.split('|')
    name='grades/'+m+'/'+i+'.json.gz'
    if (ROOT/name).exists():
        d=read(name)
    else:
        b=validated(o);raw=json.loads(b)
        if i not in raw or not isinstance(raw[i].get('resolved'),bool):
            raise ValueError(('unrecognized outcome schema',m,i,list(raw)))
        d={'model':m,'id':i,'resolved':raw[i]['resolved'],'source':o,'sha256':sha(b),'official_report':raw}
        write(name,d)
    return m+'|'+i,d

def main():
    for sub in ('','clean/'):
        lock=read(sub+'reader_lock.json')
        assert all(sha((ROOT/sub/k).read_bytes())==v for k,v in lock.items())
    lock=read('grade_lock.json');assert lock==seal(lock)
    todo=[(k,v) for k,v in read('asset_listing.json.gz').items() if k.endswith('|report.json')]
    with ThreadPoolExecutor(12) as pool:
        labels=dict(pool.map(get_one,todo))
    write('labels.json.gz',labels)
    print('labels fetched',len(labels))
if __name__=='__main__':main()
