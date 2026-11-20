import concurrent.futures,hashlib,json,os,time
from pathlib import Path
from urllib.request import urlopen,Request
ROOT=Path(__file__).resolve().parent
REPO='McGill-NLP/WebLINX'
REV='a30ff2cbecb75f2d04fac75a2b92721c6c9e3f13'
SPLITS=['train','test_iid','test_web','test_cat','test_geo','test_vis']
def get(s):
    p=ROOT/'raw'/(s+'.json.gz')
    url='https://huggingface.co/datasets/'+REPO+'/resolve/'+REV+'/data/chat/'+s+'.json.gz'
    data=urlopen(Request(url,headers={'User-Agent':'agent-memory-research'}),timeout=120).read()
    p.write_bytes(data)
    return {'split':s,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
if __name__=='__main__':
    (ROOT/'raw').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(3) as ex: rows=list(ex.map(get,SPLITS))
    (ROOT/'sources.json').write_text(json.dumps(rows,indent=1))
    print([(r['split'],r['bytes']) for r in rows])

