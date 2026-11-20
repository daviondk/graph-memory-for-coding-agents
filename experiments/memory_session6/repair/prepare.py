import ast, re, warnings
from common import *
warnings.simplefilter('ignore',SyntaxWarning)
old={r['task_id']:r for row in (ROOT/'upstream-mbpp.jsonl').read_bytes().splitlines() if (r:=json.loads(row))}
new=read('upstream-sanitized-mbpp.json')
inspected={237,280,257,223,255,277,140,94,118,272,273,172,265,77,232,251}
filter_topic=re.compile(r'password|encrypt|decrypt|cipher|network|malware|exploit|phish|firearm|weapon|bullet|viral|virus|bacteria|patient|hospital|medical|heart rate|blood pressure|\bshell\b|\battack\b',re.I)
def signature(code):
    defs=[x for x in ast.parse(code).body if isinstance(x,ast.FunctionDef)]
    if len(defs)!=1:return
    f=defs[0]; a=f.args
    if a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg or a.defaults or any(p.annotation for p in a.args) or f.returns:return
    return f.name+'('+', '.join(p.arg for p in a.args)+')'
if __name__=='__main__':
    groups={True:[],False:[]}; exclusions={}
    for r in new:
        i=r['task_id']
        if not 11<=i<=510:continue
        o=old[i]; reason=''
        try: sig=signature(r['code']); prev=signature(o['code'])
        except SyntaxError:sig=prev=None
        if i in inspected: reason='seen schema/edition example'
        elif filter_topic.search(o['text']+' '+r['prompt']):reason='topic filter'
        elif not sig or sig!=prev:reason='public interface not eligible'
        if reason:exclusions[i]=reason;continue
        groups[o['text']!=r['prompt']].append((i,sig,o['text'],r['prompt']))
    items=[]; paths=[]
    for changed, group in groups.items():
        ranked=sorted(group,key=lambda x:sha('mbpp-version6-20261118|'+str(x[0])))
        assert len(ranked)>=48
        for idx,(i,sig,historical,current) in enumerate(ranked[:48]):
            for filename,s in [('old.txt',historical),('current.txt',current),('interface.txt',sig)]:
                p=ROOT/path(i,filename);p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(s.encode()); paths.append(path(i,filename))
            items.append(dict(id=i,interface=sig,old_sha=sha(historical),current_sha=sha(current),changed=changed,
                              cohort='primary' if idx<32 else 'replication'))
    save('roster.json',dict(items=sorted(items,key=lambda x:x['id']),eligible={str(k):len(v) for k,v in groups.items()},exclusions=exclusions))
    files=paths+['protocol.md','common.py','prepare.py','infer.py','policies.py','grade.py','worker.py','runner.py','upstream-mbpp.jsonl','upstream-sanitized-mbpp.json','upstream-README.md','roster.json','tokenizer.json']
    save('design_lock.json',dict(created=stamp(),hashes=subset_hash(files)))
    print(len(items),{str(k):len(v) for k,v in groups.items()})

