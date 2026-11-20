import json,sys,hashlib
from pathlib import Path
root=Path(sys.argv[1]); logs=Path(sys.argv[2]); default=list(range(5))
def lines(p):
    return [json.loads(l) for l in p.read_text(encoding="utf8").splitlines() if l.strip()]
def norm(s):
    return ' '.join(s.casefold().split())
def swap(row):
    ids=default.copy()
    ids[row['inc']]=row['out']
    return ids
req={r['row']:r for r in lines(root/'requests.jsonl')}
out=[]
for r in lines(root/'neural_scores.jsonl'):
    i=r['row']; asked=i in req
    status='not_requested';label=None; quote='';accepted=False; usage={}
    if asked:
        raw=json.loads((logs/(req[i]['id']+'.json')).read_text(encoding="utf8"))
        status=raw['status'];usage=raw['usage']
        if status=='ok':
            try:
                obj=json.loads(raw['text']);label=obj['decision'];quote=obj['quote']
                assert label in ('A','B','both','neither') and isinstance(quote,str)
                accepted=(label==r['challenger'] and len(norm(quote))>=12 and any(norm(quote) in norm(txt) for txt in req[i]['valid_excerpts']))
                status=('accepted' if accepted else 'rejected')
            except (ValueError,KeyError,TypeError,AssertionError):
                status='invalid'
    out.append({'row':i,'eligible':r['eligible'],'asked':asked,'status':status,'label':label,'quote':quote,'usage':usage,'orders':{'parent':default,'flat_ce':r['flat'],'within_grade':r['tie'],'swap_all':swap(r) if r['eligible'] else default,'swap_submitted':swap(r) if asked else default,'verified':swap(r) if accepted else default}})
p=root/'predictions.jsonl';p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out),encoding='utf8')
print('Locked predictions SHA-256',hashlib.sha256(p.read_bytes()).hexdigest())

