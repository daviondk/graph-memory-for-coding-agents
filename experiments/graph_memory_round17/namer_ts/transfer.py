"""Preselect fixed source pairs, record prior test-file histories and freeze forecasts before labels."""
import ast
import concurrent.futures
import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from audit import CACHE, ROOT, sha, save
GIT=CACHE/'loguru'
TOOL=CACHE/'runtime/Scripts/python.exe'
COMMITS=['76355dd9','80f05fd2','3ace6db5']
FILES=['tests/test_'+x+'.py' for x in ('parse','datetime','formatting','repr','recattr','levels','bind','patch','configure',
    'add_option_level','add_option_format','add_option_colorize','ansimarkup_basic','ansimarkup_extended','get_frame')]
def git(*args):
    return subprocess.check_output(['git',*args],cwd=GIT)
def owners(text):
    tree=ast.parse(text)
    names={}
    def add(node,parts):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            parts=parts+[node.name]
            if not isinstance(node,ast.ClassDef):
                for num in range(node.lineno,node.end_lineno+1):names[num]='.'.join(parts)
        for c in ast.iter_child_nodes(node):add(c,parts)
    add(tree,[])
    return names
def plan():
    raw=json.loads((CACHE/'NameRTS/dataset/commit_pairs_loguru.json').read_bytes())
    cases=[]
    for prefix in COMMITS:
        rows=[r for r in raw if r[2].startswith(prefix) and r[3]];assert len(rows)==1
        direct,parent,current,_=rows[0]
        changed=git('diff','--name-only',parent,current,'--','loguru').decode().strip().splitlines();assert len(changed)==1
        path=changed[0];old=git('show',parent+':'+path).decode();new=git('show',current+':'+path).decode()
        before=owners(old);after=owners(new);old_names=set(before.values())
        old_lines=set();fn=set();insertion=set();fallback=False
        for op,lo,hi,l2,h2 in difflib.SequenceMatcher(None,old.splitlines(),new.splitlines(),autojunk=False).get_opcodes():
            if op=='equal':continue
            current_old=set(range(lo+1,hi+1));old_lines.update(current_old)
            attrs={before.get(n) for n in current_old}
            attrs.update(after.get(n) for n in range(l2+1,h2+1))
            if None in attrs or any(n not in old_names for n in attrs):fallback=True
            fn.update(n for n in attrs if n in old_names)
            if op=='insert':insertion.update(n for n in attrs if n in old_names)
        target=CACHE/('prior-'+parent[:12])
        if not target.exists():git('worktree','add','--detach',str(target),parent)
        assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=target).decode().strip()==parent
        assert all((target/t).is_file() for t in FILES)
        cases.append(dict(current=current,parent=parent,direct_parent=direct,path=path,source_sha=sha(old.encode()),
            new_source_sha=sha(new.encode()),old_lines=sorted(old_lines),functions=sorted(fn),insert_fallback=sorted(insertion),module_fallback=fallback))
    save('transfer-plan.json',{'pairs':cases,'files':FILES,'runner':str(TOOL),'python_version':subprocess.check_output([str(TOOL),'--version']).decode().strip(),
        'packages':subprocess.check_output(['uv','pip','freeze','--python',str(TOOL)]).decode().splitlines()})
    save('transfer-plan.lock.json',{n:sha((ROOT/n).read_bytes()) for n in ('TRANSFER_PROTOCOL_RU.md','warm_file.py','transfer.py','transfer-plan.json')})
def run_one(inp):
    pair,file=inp; base=pair['parent']; prior=CACHE/('prior-'+base[:12]);reports=CACHE/'executions'/base;reports.mkdir(parents=True,exist_ok=True)
    name=Path(file).stem
    report=reports/(name+'.json');log=reports/(name+'.log')
    if not report.exists():
        result=subprocess.run([str(TOOL),str(ROOT/'warm_file.py'),str(prior),file,pair['path'],str(report)],cwd=prior,env={**os.environ,'PYTHONUTF8':'1'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
        log.write_bytes(result.stdout)
        if result.returncode!=0:raise AssertionError((file,result.returncode,result.stdout[-220:]))
    objective=json.loads(report.read_bytes())
    code=objective['status']
    passing={e[0] for e in objective['tests'] if e[1]=='call' and e[2]=='passed'}
    clean=code==0 and bool(passing) and not any(e[2]=='failed' for e in objective['tests'])
    called=set(objective['calls']);executed=set(objective['lines'])
    loaded=bool(called or executed)
    dur=objective['seconds']
    methods={
        'module':loaded,
        'function':(loaded if pair['module_fallback'] else bool(called & set(pair['functions']))),
        'line':(loaded if pair['module_fallback'] else bool(executed & set(pair['old_lines']) or called & set(pair['insert_fallback'])))}
    if not clean:methods=dict.fromkeys(methods,True)
    return dict(current=pair['current'],parent=base,file=file,clean=clean,native_code=code,pass_count=len(passing),loaded=loaded,
            select=methods,runtime=objective,raw_log=log.read_text(encoding='utf8',errors='replace'),raw_log_sha=sha(log.read_bytes()))
def run():
    for n,h in json.loads((ROOT/'transfer-plan.lock.json').read_bytes()).items():assert sha((ROOT/n).read_bytes())==h
    pairs=json.loads((ROOT/'transfer-plan.json').read_bytes())['pairs']
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:
        rows=list(e.map(run_one,[(p,f) for p in pairs for f in FILES]))
    save('transfer-predictions.json.gz',rows)
    save('transfer-seal.json',{n:sha((ROOT/n).read_bytes()) for n in ('transfer-plan.lock.json','transfer-predictions.json.gz')})
    print('native pytest',len(rows),'clean',sum(r['clean'] for r in rows),flush=True)
if __name__=='__main__':{'plan':plan,'run':run}[sys.argv[1]]()
