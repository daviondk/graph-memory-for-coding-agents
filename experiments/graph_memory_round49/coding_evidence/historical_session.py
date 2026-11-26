"""Run before the target session in its clean official image. Retain only Python call coordinates."""
import collections,json,os,sys
from pathlib import Path
import pandas as pd
import woodwork
repo=Path(woodwork.__file__).resolve().parent
edges=collections.Counter();visits=collections.Counter();events=[]
def ident(f):
    if f is None:return None
    p=Path(f.f_code.co_filename)
    try: rel=p.relative_to(repo)
    except ValueError:return None
    if p.suffix!='.py' or 'tests' in rel.parts or f.f_code.co_name.startswith('<'):return None
    return ('woodwork/'+rel.as_posix(),f.f_code.co_firstlineno,f.f_code.co_name)
def observe(f,event,arg):
    if event!='call':return
    v=ident(f)
    if v is None:return
    visits[v]+=1;u=ident(f.f_back)
    if u is not None:edges[u,v]+=1
def step(name,fn):
    try:fn();events.append([name,'ok'])
    except Exception as e:events.append([name,type(e).__name__])
sample=pd.DataFrame({'category':['a','b','a'],'value':[11,12,13]})
sys.setprofile(observe)
step('initialize',lambda:sample.ww.init())
step('one-column',lambda:sample.ww['category'])
step('two-columns',lambda:sample.ww[['value','category']])
step('schema',lambda:sample.ww.schema)
step('copy',lambda:sample.copy())
step('logical-types',lambda:sample.ww.logical_types)
sys.setprofile(None)
print(json.dumps({'actions':events,'visits':[[list(k),v] for k,v in sorted(visits.items())],'calls':[[list(a),list(b),n] for (a,b),n in sorted(edges.items())]}))
