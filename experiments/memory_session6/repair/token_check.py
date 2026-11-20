import requests
from common import *
from infer import tokens, URL
out={}
for i in (r['id'] for r in read('roster.json')['items']):
    p=read(path(i,'prefix.json'))
    for s in (p['raw'],p['note']):
        if sha(s) in out:continue
        res=requests.post(URL+'/tokenize',json=dict(content=s,add_special=False,parse_special=False),timeout=10)
        res.raise_for_status();native=res.json()['tokens']
        assert native==tokens(s) and len(native)<=40
        out[sha(s)]=native
save('runtime/tokenizer_crosscheck.json.gz',{'created':stamp(),'native_token_ids':out})
print(len(out),'distinct carried memories, exact native token IDs')

