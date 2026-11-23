"""Audit author ranking lists, common-base counts, source control hashes and published file protocol."""
import ast
import gzip
import json
from pathlib import Path
import subprocess
from audit import CACHE, REV, ROOT, save, sha

def load(n):
    b=(ROOT/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
def main():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=CACHE/'NameRTS').decode().strip()==REV
    t=load('transfer-results.json')
    for n,h in load('transfer-seal.json').items():assert sha((ROOT/n).read_bytes())==h
    for n,h in load('transfer-plan.lock.json').items():assert sha((ROOT/n).read_bytes())==h
    for k,s in load('transfer-label-sources.json').items():
        assert sha((CACHE/'NameRTS'/s['path']).read_bytes())==s['sha256']
    a=load('pairs.json.gz');ids=[x for x in a if x['changed']['true_parent']]
    assert len(a)==50 and len(ids)==5 and all(len(x['methods']['NameRTS']['selected_files'])==102 for x in ids)
    assert sum(len(x['ground_truth']) for x in ids)==34
    for x in ids:
        assert set(x['methods']['NameRTS']['selected_files'])==set(x['methods']['EkstaP']['selected_files'])
    r=load('transfer-predictions.json.gz');assert len(r)==45 and all(x['clean'] for x in r)
    for rec in t['pairs']:
        assert set(rec['selected']['all']['chosen'])<=set(rec['selected']['EkstaP']['chosen'])
        assert rec['full_selection_counts']['EkstaP']==rec['official_n']
    f=CACHE/'NameRTS/src/utils.py'; tree=ast.parse(f.read_bytes())
    func=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='is_test_file_pytest')
    # Execute the pinned predicate only, without configuration or external job runners.
    module=ast.Module(body=[func],type_ignores=[]);scope={'Path':Path}
    exec(compile(module,str(f),'exec'),scope)
    inputs=['colorama/tests/ansi_test.py','colorama/tests/ansitowin32_test.py','tests/test_datetime.py','tests/test_parse.py']
    verdict={f:scope['is_test_file_pytest'](f,'') for f in inputs}
    assert list(verdict.values())==[False,False,True,True]
    save('colorama-adapter.json',{'upstream_sha':sha(f.read_bytes()),'function':'is_test_file_pytest','lines':[func.lineno,func.end_lineno],'outcomes':verdict,
         'scope':'component only; initial pytest collection and complete NameRTS not invoked on Colorama'})
    print('50 reference pairs/5 AST matches; 45 native warm files and 3 matched external label sets; Colorama predicate',verdict)
if __name__=='__main__':main()
