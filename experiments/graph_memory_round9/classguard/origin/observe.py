"""Observe real class construction paths independently of mutable public module names."""
import builtins
import json
import sys
from pathlib import Path
import pytest


def main():
    root=Path.cwd().resolve();prefix=root/"sympy"
    sys.path.insert(0,str(root))
    nodes,target=map(Path,sys.argv[1:3])
    records={};origins={}
    original=builtins.__build_class__
    def observe_class(fn,name,*bases,**kw):
        obj=original(fn,name,*bases,**kw)
        if hasattr(fn,"__code__") and isinstance(obj,type):
            raw=fn.__code__.co_filename
            if raw and not raw.startswith("<"):
                path=Path(raw).resolve()
                if path.is_relative_to(prefix) and "tests" not in path.relative_to(root).parts:
                    origins[id(obj)]=(obj,path.relative_to(root).as_posix()+"|"+fn.__qualname__)
        return obj
    def key(cls):
        if id(cls) in origins and origins[id(cls)][0] is cls:return origins[id(cls)][1]
        mod=sys.modules.get(cls.__module__)
        if not getattr(mod,"__file__",None):return None
        f=Path(mod.__file__).resolve()
        if not f.is_relative_to(prefix) or "tests" in f.relative_to(root).parts:return None
        return f.relative_to(root).as_posix()+"|"+cls.__qualname__
    class Observe:
        def pytest_collection_finish(self,session):
            for item in session.items:
                fn=getattr(item,"function",None)
                direct=set();ancestors=set();seen=[]
                if hasattr(fn,"__code__"):
                    for sym in set(fn.__code__.co_names):
                        if sym not in fn.__globals__:continue
                        obj=fn.__globals__[sym]
                        cls=obj if isinstance(obj,type) else type(obj)
                        owner=key(cls)
                        if owner:direct.add(owner);seen.append(sym)
                        for typ in cls.__mro__:
                            on=key(typ)
                            if on:ancestors.add(on)
                records[item.nodeid]=dict(direct=sorted(direct),ancestors=sorted(ancestors),globals=sorted(seen))
    builtins.__build_class__=observe_class
    try:
        code=pytest.main(["-q","--collect-only","-o","addopts=","--disable-warnings",*json.loads(nodes.read_bytes())],plugins=[Observe()])
    finally:
        builtins.__build_class__=original
    target.write_text(json.dumps(dict(code=int(code),records=records,n_created_classes=len(origins)),sort_keys=True)+"\n",encoding="utf8")
if __name__=="__main__":main()
