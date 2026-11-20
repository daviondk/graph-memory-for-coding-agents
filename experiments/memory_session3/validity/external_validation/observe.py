"""One release, real public API calls; isolate package imports per command."""
import collections, functools, gc, importlib, itertools, json, os, platform, re, sys, time, warnings
from pathlib import Path
from sources import ROOT,canon,tree,save,sha
warnings.simplefilter('ignore')
def normalize(v,level=0):
    if isinstance(v,bytes):return {'bytes_hex':v.hex()}
    if v is None or isinstance(v,(int,float,bool,str)):return v
    if isinstance(v,dict):return {str(k):normalize(sub,level+1) for k,sub in v.items()}
    if isinstance(v,(set,frozenset)):return sorted([normalize(x,level+1) for x in v],key=canon)
    if level<4 and hasattr(v,'__iter__'):return [normalize(x,level+1) for x in itertools.islice(v,128)]
    return re.sub(r'0x[0-9a-fA-F]+','0xADDR',str(v))
def resolve(r):
    mod=importlib.import_module(r['pkg']+('.'+r['module'] if r['module'] else ''))
    return getattr(mod,r['function'])
def binding(fn):
    raw=getattr(fn,'__wrapped__',fn)
    return [getattr(raw,'__module__',None),getattr(raw,'__qualname__',type(raw).__qualname__)]
def clean(pkg):
    for name in list(sys.modules):
        if name==pkg or name.startswith(pkg+'.'):sys.modules.pop(name,None)
def value(r,fn):
    try:
        if fn is None:fn=resolve(r)
        v=fn(*r['args'],**r['kwargs'])
        if r['format']=='str':v=str(v)
        if r['format']=='pattern':
            rx=getattr(v,'regex',None)
            v=[getattr(rx,'pattern',None),getattr(v,'include',None)]
        if r['format']=='plain' and isinstance(v,dict):
            # Canonicalize date/time leaves across Python processes.
            v={k:(q.isoformat() if callable(getattr(q,'isoformat',None)) else q) for k,q in v.items()}
        if r['format']=='wheel':v=[str(v[0]),str(v[1]),list(v[2]),sorted(map(str,v[3]))]
        return ['return',normalize(v)]
    except Exception as exc:
        s=re.sub(r'0x[0-9a-fA-F]+','0xADDR',str(exc))
        return ['exception',type(exc).__module__+'.'+type(exc).__qualname__,s]
def main(pkg,v,mode):
    base=tree(pkg,v); sys.path.insert(0,str(base))
    envp=str(base.resolve()).replace('\\','/').lower()+'/'
    pathnames={}
    def file(code):
        path=code.co_filename
        if path not in pathnames:
            s=path.replace('\\','/'); pathnames[path]=s[len(envp):] if s.lower().startswith(envp) else None
        return pathnames[path]
    rows=[];obs=ROOT/'runs'/pkg/v;obs.mkdir(parents=True,exist_ok=True)
    for r in json.loads((ROOT/'roster.json').read_text(encoding='utf8')):
        if r['pkg']!=pkg:continue
        clean(pkg); t=time.perf_counter_ns()
        try:fn=resolve(r); entry=binding(fn)
        except AttributeError:fn=None;entry=None
        loaded=time.perf_counter_ns()
        coverage=collections.defaultdict(set)
        def oncall(f,event,arg):
            rel=file(f.f_code)
            if event!='call' or not rel:return
            k=(rel,f.f_code.co_qualname,f.f_code.co_firstlineno)
            def onframe(frame,event,arg):
                if event=='line':coverage[k].add(frame.f_lineno)
                return onframe
            return onframe
        if mode=='traced':sys.settrace(oncall)
        try:result=value(r,fn)
        finally:sys.settrace(None)
        elapsed=time.perf_counter_ns()
        rows.append({'key':r['key'],'entry':entry,'value':result,'load_ns':loaded-t,'run_ns':elapsed-loaded,'covered':[[*k,sorted(s)] for k,s in sorted(coverage.items())]})
    save(obs/(mode+'.json'),rows)
if __name__=='__main__':main(*sys.argv[1:])

