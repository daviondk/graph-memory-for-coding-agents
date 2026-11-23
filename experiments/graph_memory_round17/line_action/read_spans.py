"""Perform actual bounded reads from the base revision for LLM and lexical choices before scoring."""
from collections import defaultdict
from pathlib import Path
import json
import time
import urllib.parse

from study import ROOT, INPUT, read, put, sha, lock
CACHE=Path("D:/CodexResearch/x20-anchor-transfer/base")

def main():
    lock(ROOT/'response.lock.json')
    menus={q['id']:q for q in read(ROOT/'menus.json.gz')}
    calls={r['sha']:r for r in (json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines())}
    sources={(r['instance_id'],r['source']):r for r in read(INPUT/'observations.json.gz')}
    actions=[]
    for row in read(ROOT/'assignment.json'):
        iid=row['id'];q=menus[iid];arm=row['arm'];menu=q['menus'][arm]
        source=sources[iid,q['source']]['views'][:3]
        for solver,choice in [('qwen',calls[row['sha']]['choice']),('lexical',row['lexical_choice'])]:
            event={'id':iid,'source':q['source'],'repo':q['repo'],'solver':solver,'arm':arm,'choice':choice,'sha':row['sha'],'region':[]}
            if choice is not None:
                spot=menu[choice];path=spot['p']
                url='https://raw.githubusercontent.com/'+q['repo']+'/'+q['base']+'/'+urllib.parse.quote(path,safe='/')
                binary=CACHE/sha(url.encode())
                start=time.perf_counter()
                data=binary.read_bytes();hash_value=sha(data)
                expected={v['base_blob_sha256'] for v in source if v['path']==path and v['base_status']=='match'}
                assert expected=={hash_value}
                code=data.decode('utf8').splitlines()[spot['s']-1:spot['e']]
                assert code==spot['lines'],(iid,choice)
                event.update({'bytes_read':len(data),'seconds':time.perf_counter()-start,'base_blob_sha256':hash_value,'url':url,
                              'selected_bytes':len('\n'.join(code).encode()),'region':[[path,spot['s'],spot['e']]]})
            actions.append(event)
    put('actions.json.gz',actions)
    put('read.lock.json',{n:sha((ROOT/n).read_bytes()) for n in ('read_spans.py','response.lock.json','actions.json.gz')})
    print('physical reads:',sum(bool(a['region']) for a in actions),'/',len(actions),flush=True)

if __name__=='__main__':
    main()
