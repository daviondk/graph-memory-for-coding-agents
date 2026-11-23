"""Physically read each chosen region against immutable base Git data."""
import json
from collections import Counter
from pathlib import Path
import urllib.parse

from gate import INPUT,ROOT,read,put,sha

def main():
    for n,h in read(ROOT/'response.lock.json').items():assert sha((ROOT/n).read_bytes())==h
    menu={r['id']:r for r in read(ROOT/'menus.json.gz')}
    sources={(r['instance_id'],r['source']):r['views'][:3] for r in read(INPUT/'observations.json.gz')}
    calls={r['sha']:r for r in (json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines())}
    out=[]
    for row in read(ROOT/'route.json'):
        i=row['id'];r=menu[i];q=calls.get(row['sha'])
        entry={'id':i,'source':r['source'],'repo':r['repo'],'available':bool(row['sha']),'cost':q['usage'] if q else {}}
        for method,choice in [('qwen',(q or {}).get('choice')),('static',row['static_choice'])]:
            data={'choice':choice,'region':[]}
            if choice:
                spot=r['menu'][choice];path=spot['p']
                uri='https://raw.githubusercontent.com/'+r['repo']+'/'+r['base']+'/'+urllib.parse.quote(path,safe='/')
                raw=(Path('D:/CodexResearch/x20-anchor-transfer/base')/sha(uri.encode())).read_bytes()
                expected={v['base_blob_sha256'] for v in sources[i,r['source']] if v['path']==path and v['base_status']=='match'}
                assert expected=={sha(raw)}
                lines=raw.decode('utf8').splitlines()[spot['s']-1:spot['e']]
                assert lines==spot['lines']
                data.update(region=[[path,spot['s'],spot['e']]],sha256=sha(raw),bytes_read=len(raw),bytes_selected=len('\n'.join(lines).encode()))
            entry[method]=data
        out.append(entry)
    put('actions.json.gz',out)
    put('read.lock.json',{n:sha((ROOT/n).read_bytes()) for n in ('execute.py','actions.json.gz','response.lock.json')})
    print({k:sum(bool(r[k]['region']) for r in out) for k in ('qwen','static')},flush=True)
if __name__=='__main__':main()
