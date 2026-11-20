"""Check per-submission public feedback envelope without retaining assistant messages or output text."""
import hashlib,json,urllib.request,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
ROOT=Path(__file__).resolve().parent
def one(src):
    raw=urllib.request.urlopen(src['url'],timeout=60).read()
    obj=json.loads(raw);normal=Counter();form=Counter()
    for m in obj['messages']:
        if m.get('role')=='tool' or m.get('type')=='function_call_output':
            ex=m.get('extra',{});rc=ex.get('returncode')
            text=m.get('content',m.get('output',''))
            if not isinstance(rc,int) or not isinstance(text,str):continue
            xml=bool(re.search(r'<returncode>\s*'+str(rc)+r'\s*</returncode>',text,re.I))
            explicit=bool(re.search(r'(?:returncode|return code|exit code)\s*[\x22\x27:>= ]+\s*'+str(rc)+r'\b',text,re.I))
            normal[str(rc!=0)]+=1;form['xml' if xml else 'other_explicit' if explicit else 'unknown']+=1
    return {'model':src['model'],'issue':src['id'],'url':src['url'],'sha256':hashlib.sha256(raw).hexdigest(),'rc_key_nonzero_counts':normal,'public_rc_forms':form}
if __name__=='__main__':
    source=json.loads((ROOT.parent/'list.json').read_bytes())
    sample=[min([r for r in source if r['model']==m],key=lambda r:hashlib.sha256(('failure-wire|'+r['id']).encode()).digest()) for m in ['claude','gemini','codex']]
    with ThreadPoolExecutor(3) as pool:out=list(pool.map(one,sample))
    (ROOT/'wire_audit.json').write_text(json.dumps(out,indent=1),encoding='utf8');print(out)

