"""One original pytest process on the selected release. Source instrumentation stays in memory."""
import ast
import builtins
import collections
import importlib.abc
import importlib.util
import math
import operator
import os
import sys
from pathlib import Path

from core import OP,get,put
import pytest

def run(config_path):
    config=get(Path(config_path));repo=Path(config["repo"]).resolve();tests=Path(config["tests"]).resolve()
    table=get("roster.json")["sites"];version=config["version"];mode=config["mode"];target=config.get("target")
    coords=collections.defaultdict(dict);lines=collections.defaultdict(lambda:collections.defaultdict(list))
    for s in table:
        rec=s[version];file=str(repo/"boltons"/(rec["module"]+".py"))
        coords[file][(rec["line"],rec["column"])]=(s["id"],rec["op"])
        lines[file][rec["line"]].append(s["id"])
    active=None;events=collections.defaultdict(lambda:collections.defaultdict(set))
    def observe(site,left,right,op):
        if active is not None:
            flags=events[active][site];flags.add("predicate")
            if type(left) in (float,int) and type(right) in (float,int):
                if (type(left) is int or math.isfinite(left)) and (type(right) is int or math.isfinite(right)):
                    flags.add("numeric")
                    if left==right:flags.add("equal")
        return {"Lt":operator.lt,"LtE":operator.le,"Gt":operator.gt,"GtE":operator.ge}[op](left,right)
    def trace(frame,event,arg):
        lookup=lines.get(frame.f_code.co_filename)
        if lookup is None:return None
        if event=="line" and active is not None:
            for s in lookup.get(frame.f_lineno,[]):events[active][s].add("line")
        return trace
    class Rewrite(ast.NodeTransformer):
        def __init__(self,file):self.entries=coords[file]
        def visit_Compare(self,node):
            self.generic_visit(node);item=self.entries.get((node.lineno,node.col_offset))
            if not item:return node
            site,op=item;assert len(node.ops)==1 and type(node.ops[0]).__name__==op
            if mode=="history":
                call=ast.Call(func=ast.Name(id="_r19_number_observation",ctx=ast.Load()),args=[ast.Constant(site),node.left,node.comparators[0],ast.Constant(op)],keywords=[])
                return ast.copy_location(call,node)
            if mode=="mutant" and target==site:node.ops=[getattr(ast,OP[op])()]
            return node
    class Source(importlib.abc.Loader):
        def __init__(self,file):self.file=file
        def create_module(self,spec):return None
        def exec_module(self,module):
            tree=ast.parse(Path(self.file).read_bytes(),filename=self.file)
            tree=ast.fix_missing_locations(Rewrite(self.file).visit(tree));module.__dict__["_r19_number_observation"]=observe
            exec(compile(tree,self.file,"exec"),module.__dict__)
    class Loader(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path,target=None):
            parts=fullname.split(".")
            if len(parts)!=2 or parts[0]!="boltons":return None
            f=str(repo/"boltons"/(parts[1]+".py"))
            return importlib.util.spec_from_file_location(fullname,f,loader=Source(f)) if f in coords else None
    sys.path.insert(0,str(repo));os.chdir(tests)
    if mode in ("history","mutant"):sys.meta_path.insert(0,Loader())
    import boltons
    assert any(Path(p).resolve()==repo/"boltons" for p in boltons.__path__)
    statuses={};selected=[];errors=[]
    class Capture:
        def pytest_collection_finish(self,session):selected.extend(item.nodeid for item in session.items)
        def pytest_collectreport(self,report):
            if report.failed:errors.append(report.nodeid)
        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_call(self,item):
            nonlocal active
            active=item.nodeid;prev=sys.gettrace()
            if mode=="history":sys.settrace(trace)
            try:yield
            finally:
                if mode=="history":sys.settrace(prev)
                active=None
        def pytest_runtest_logreport(self,report):
            if report.when=="call":statuses[report.nodeid]=report.outcome
            elif report.failed:statuses[report.nodeid]=report.when+"_error"
    args=["-p","no:cacheprovider","--import-mode=importlib","--rootdir="+str(tests),"-q","--disable-warnings","--tb=no",*config["nodes"]]
    ret=pytest.main(args,plugins=[Capture()])
    put(Path(config["output"]),{"code":int(ret),"collection_errors":errors,"selected":selected,"status":statuses,
                                "events":{tid:{s:sorted(v) for s,v in m.items()} for tid,m in events.items()}})
if __name__=="__main__":run(sys.argv[1])
