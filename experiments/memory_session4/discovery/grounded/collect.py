"""Resolve missing UID with separately recorded current geometry, blind to reference action."""
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
import gzip,hashlib,json,re,time
ROOT=Path(__file__).resolve().parent
REV='36ef9f79b43df50e25b7f3b68e5c9f6ccf4160e8'
def sha(x):return hashlib.sha256(x).hexdigest()
def fetch(d,suffix):
    path='https://huggingface.co/datasets/McGill-NLP/WebLINX-full/resolve/'+REV+'/demonstrations/'+d+'/'+suffix
    for i in range(4):
        try:
            with urlopen(Request(path,headers={'User-Agent':'WebLINX-memory-evaluation','Accept-Encoding':'gzip'}),timeout=25) as reply:
                raw=reply.read(); data=gzip.decompress(raw) if reply.getheader('Content-Encoding')=='gzip' else raw
                return json.loads(data),{'object':suffix,'http':200,'sha256':sha(data),'body_bytes':len(data),'wire_bytes':len(raw)}
        except HTTPError as ex:
            if ex.code in (401,403,404):return None,{'object':suffix,'http':ex.code}
            fail=type(ex).__name__
        except (TimeoutError,URLError,ValueError,ConnectionError) as ex:fail=type(ex).__name__
        time.sleep(i+1)
    return None,{'object':suffix,'error':fail}
def collect(item):
    d,group=item;out=ROOT/'receipts'/(d+'.json')
    if out.exists():return
    idx=defaultdict(list)
    for r in group:idx[r['i']].append(r)
    rep,receipt=fetch(d,'replay.json');blobs=[receipt];cache={};positions={};rows=[]
    for i in sorted(idx):
        state=rep['data'][i].get('state',{}) if rep else {};fname=state.get('page') or ''
        match=re.search(r'page-(\d+)-\d+\.html',fname);n=int(match[1]) if match else None
        if n is not None and n not in cache:
            cache[n],meta=fetch(d,'bboxes/bboxes-'+str(n)+'.json');blobs.append(meta)
        for query in idx[i]:
            bbox=(cache.get(n) or {}).get(query['old']);presence=(bbox is not None) if cache.get(n) is not None else None
            rect=[bbox.get(k,0) for k in ('left','top','right','bottom')] if bbox else None
            visible=None
            if presence is not None:
                visible=False
                if rect and query['w'] and query['h']:
                    l,t,r,b=rect;visible=min(r,query['w'])>max(l,0) and min(b,query['h'])>max(t,0)
            rows.append({'s':query['s'],'d':d,'i':i,'page':fname,'bbox_index':n,'rect':rect,'present':presence,'visible':visible})
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps({'id':d,'file_receipts':blobs,'probes':rows},separators=(',',':')));tmp.replace(out)
def main():
    locks=json.loads((ROOT/'input_lock.json').read_bytes());assert all(sha((ROOT/f).read_bytes())==h for f,h in locks.items())
    groups=defaultdict(list)
    for r in json.loads((ROOT/'queries.json').read_bytes()):groups[r['d']].append(r)
    (ROOT/'receipts').mkdir(exist_ok=True)
    with ThreadPoolExecutor(6) as pool:list(pool.map(collect,sorted(groups.items())))
    paths=sorted((ROOT/'receipts').glob('*.json'));assert len(paths)==len(groups)
    (ROOT/'output_lock.json').write_text(json.dumps({f.relative_to(ROOT).as_posix():sha(f.read_bytes()) for f in paths},indent=1))
    print('retrieved',len(paths))
if __name__=='__main__':main()

