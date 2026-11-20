"""Schema projection from fixed SWE-smith parquet. No evaluation outcomes used to select instances."""
import gzip, hashlib, json, re, sys
from pathlib import Path
from collections import Counter,defaultdict
from common import ROOT,rel,printed,success

OLD=ROOT.parents[1]/'memory_session4'/'compact'
sys.path.insert(0,str(OLD/'.scratch/lib'))
import pyarrow.parquet as pq
import parent_extract as native
# Import only the prior two message-parser functions.
ALLOWED=set("""HIPS__autograd Suor__funcy PyCQA__flake8 adrienverge__yamllint agronholm__exceptiongroup agronholm__typeguard alecthomas__voluptuous amueller__word_cloud andialbrecht__sqlparse arrow-py__arrow chardet__chardet cknd__stackprinter dask__dask davidhalter__parso dbader__schedule django-money__django-money erikrose__parsimonious facebookresearch__fvcore facebookresearch__hydra facelessuser__soupsieve gawel__pyquery google__textfsm gweis__isodate hukkin__tomli jaraco__inflect jawah__charset_normalizer jd__tenacity joke2k__faker jsvine__pdfplumber kayak__pypika keleshev__schema life4__textdistance lincolnloop__python-qrcode luozhouyang__python-string-similarity mahmoud__boltons mahmoud__glom marshmallow-code__marshmallow matthewwithanm__python-markdownify mido__mido modin-project__modin mozillazg__python-pinyin msiemens__tinydb pallets__click pandas-dev__pandas prettytable__prettytable pydantic__pydantic pydata__patsy pygments__pygments pylint-dev__astroid python-jsonschema__jsonschema python-openxml__python-docx python__mypy pyutils__line_profiler r1chardj0n3s__parse rsalmei__alive-progress rubik__radon rustedpy__result scanny__python-pptx seatgeek__thefuzz seperman__deepdiff spulec__freezegun sqlfluff__sqlfluff sunpy__sunpy tkrajina__gpxpy tobymao__sqlglot tox-dev__pipdeptree un33k__python-slugify""".split())
BAN=re.compile(r'\b(?:CVE[- ]?\d*|exploit(?:ation)?|vulnerabilit\w*|intrusion|payload injection|SQL injection|remote code execution|command injection|deserialization attack|privilege escalation|cross.site scripting|XSS|arbitrary code execution|shellcode|malware|sandbox escape|auth bypass)\b',re.I)
def h(x):return hashlib.sha256(x.encode()).hexdigest()
def dump(n,x): (ROOT/n).write_text(json.dumps(x,ensure_ascii=True,indent=1))
def issue_text(t):
    if '<pr_description>' in t:return t.partition('<pr_description>')[2].partition('</pr_description>')[0]
    return t[:10000]
def wrap(v):return v.removeprefix('\n').removesuffix('\n')
def decode(r,k,i):
    obj=native.convert(r,k,i);ms=json.loads(r['messages']);source='native'
    if not any(m['role']=='tool' for m in ms):
        source='tagged';prev=None;ev=[]
        for m in ms:
            if m['role']=='assistant':
                fs=list(re.finditer(r'<function=([\w.-]+)>(.*?)</function>',native.textparts(m.get('content')),re.S))
                if len(fs)==1:
                    name,b=fs[0].groups();prev=[name,{a:wrap(v) for a,v in re.findall(r'<parameter=([\w.-]+)>(.*?)</parameter>',b,re.S)}]
                else:prev=['unresolved',{}]
            if m['role']=='user' and prev is not None:ev.append([*prev,native.textparts(m.get('content'))]);prev=None
        obj['events']=ev
    obj['issue']=issue_text(obj['issue']);obj['format']=source
    if BAN.search(obj['issue']):return None
    # Store opaque placeholders for shell commands; no raw shell action or unrelated free-form observations needed.
    clean=[]
    for name,args,obs in obj['events']:
        if name not in ('str_replace_editor','str_replace_based_edit_tool','edit_file') or not isinstance(args,dict):
            clean.append(['other',{},'']);continue
        path=rel(args.get('path',''));cmd=args.get('command','')
        if BAN.search(path):return None
        if BAN.search(str(args.get('old_str',''))) or BAN.search(str(args.get('new_str',''))):return None
        lines=printed(obs);msg='The file snapshot has been edited.\n' if success(cmd,path,obs) else ''
        only={q:args[q] for q in ['path','command','old_str','new_str'] if q in args}
        clean.append([name,only,msg+'\n'.join(str(n)+'\t'+v for n,v in lines.items())])
    obj['events']=clean;return obj
def main():
    refs=json.loads((ROOT/'shards.json').read_bytes()); candidates=defaultdict(list);all_old=set()
    for k,it in enumerate(refs):
        old=OLD/'source'/f'{k}.jsonl.gz'
        for l in gzip.open(old,'rt',encoding='utf8'):all_old.add(json.loads(l)['instance'])
        src=OLD/'.scratch'/Path(it['path']).name
        with src.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==it['lfs']['oid']
        pf=pq.ParquetFile(src);i=0
        for batch in pf.iter_batches(batch_size=1000,columns=['instance_id','traj_id']):
            for row in batch.to_pylist():
                s=row['instance_id']; repo=s.split('.')[0]
                if repo in ALLOWED and int(h('compact-s4|'+s),16)%10!=0 and s!='django-money__django-money.835c1ab8.func_pm_ctrl_shuffle__viqnyl9u':
                    candidates[s].append((h('s5-traj|'+str(row['traj_id'])+'|'+str(k)+'|'+str(i)),k,i))
                i+=1
        pf.close()
    sel=defaultdict(list)
    for s,choices in sorted(candidates.items(),key=lambda kv:h('s5-task|'+kv[0])):
        repo=s.split('.')[0];split='test' if int(h('s5-repo|'+repo),16)%3==0 else 'train'
        if len(sel[split])<1350:sel[split].append((s,*min(choices)[1:]))
    assert all(s not in all_old for rs in sel.values() for s,k,i in rs)
    dump('selection.json',sel);pick={(k,i):split for split,rs in sel.items() for _,k,i in rs};co=Counter()
    for k,it in enumerate(refs):
        handles={}
        for split in sel:
            (ROOT/'source'/split).mkdir(parents=True,exist_ok=True)
            handles[split]=gzip.open(ROOT/'source'/split/f'{k}.jsonl.gz','wt',encoding='utf8',compresslevel=3)
        pf=pq.ParquetFile(OLD/'.scratch'/Path(it['path']).name);idx=0
        for b in pf.iter_batches(batch_size=24,columns=['instance_id','traj_id','messages','model'],use_threads=False):
            for j in range(b.num_rows):
                split=pick.get((k,idx))
                if split:
                    row=b.slice(j,1).to_pylist()[0];obj=decode(row,k,idx)
                    if obj is not None:
                        print(json.dumps(obj,ensure_ascii=True,separators=(',',':')),file=handles[split]);co[split+'_'+obj['format']]+=1
                    else:co[split+'_excluded']+=1
                idx+=1
        pf.close()
        for f in handles.values():f.close()
        print('shard',k,dict(co),flush=True)
    dump('extraction.json',dict(co))
if __name__=='__main__':main()
