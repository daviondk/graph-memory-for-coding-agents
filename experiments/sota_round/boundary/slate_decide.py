import json,sys
from pathlib import Path
from slate import read,write
base,out,logs=map(Path,sys.argv[1:4]); pred=read(base/'predictions.jsonl'); req=read(out/'requests.jsonl')
def fold(s):return ' '.join(s.casefold().split())
for p in pred:
    p['asked']=False
    for method in ['slate','slate_raw','forced_64']:
        p['orders'][method]=list(range(5))
for r in req:
    p=pred[r['row']];p['asked']=True;data=json.loads((logs/(r['id']+'.json')).read_text(encoding='utf8'))
    p['status']=data['status'];p['usage']=data['usage'];a,b=r['forced'];p['orders']['forced_64'][a]=b
    if data['status']!='ok':continue
    try:
        obj=json.loads(data['text']);d=obj['drop'];a=obj['add']
        if d is None and a is None:p['status']='keep';continue
        x,y=r['map'][d],r['map'][a]
        assert x<5<=y
        p['orders']['slate_raw'][x]=y
        q=fold(obj['quote']);p['quote']=obj['quote']
        if len(q)>=12 and any(q in fold(s) for s in r['witness'][a]):
            p['orders']['slate'][x]=y;p['status']='swap'
        else:p['status']='unverified'
    except (AssertionError,KeyError,TypeError,ValueError,AttributeError):
        p['status']='invalid'
write(out/'predictions.jsonl',pred)

