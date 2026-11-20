"""Descriptive case mix after labels. No policy refit."""
from collections import Counter,defaultdict
from pathlib import PurePosixPath
import numpy as np
from common13 import D,read,dump,sha
def main():
    rows=read(D/'features.json.gz');oracle=read(D/'direct_receipts.json');shape=defaultdict(Counter);n=len(rows);y=np.array([oracle[r['id']]['hit'] for r in rows],bool)
    for r in rows:
        k=oracle[r['id']]['scope_kind'];alias='generic' if r['root']=='/testbed' else 'named';a=r['trust'];hit=oracle[r['id']]['hit'];cell=shape[k+'/'+alias]
        cell.update(n=1,unsafe=int(hit),same_scope=int(a['scope_content']),same_scope_unsafe=int(a['scope_content'] and hit),fresh_scope_strict=int(a['fresh_scope_strict']),fresh_scope_strict_unsafe=int(a['fresh_scope_strict'] and hit))
    orders={'named+syntactic_file':sorted(range(n),key=lambda i:(rows[i]['root']=='/testbed',not bool(PurePosixPath(rows[i]['scope']).suffix),sha(rows[i]['id'].encode()))),'named+actual_file':sorted(range(n),key=lambda i:(rows[i]['root']=='/testbed',oracle[rows[i]['id']]['scope_kind']!='file',sha(rows[i]['id'].encode())))}
    curves={}
    for method,order in orders.items():
        cum=np.cumsum(y[order]);curves[method]={'aurc':float(np.mean(cum/np.arange(1,n+1))),'counts':{str(f):int(cum[round(n*f)-1]) for f in [.1,.25,.5,.75,.9,1]}}
    dump(D/'scope_diagnostic.json',dict(strata=shape,rank_controls=curves))
if __name__=='__main__':main()