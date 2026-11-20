"""Record Python classes of globals directly referenced by each already collected test."""
import json
import sys
from pathlib import Path
import pytest


def main():
    root=Path.cwd().resolve()
    sys.path.insert(0,str(root))
    nodes,target=map(Path,sys.argv[1:3])
    records={}
    def key(cls):
        mod=sys.modules.get(cls.__module__)
        name=getattr(mod,"__file__",None)
        if not name:return None
        f=Path(name).resolve()
        if not f.is_relative_to(root/"sympy") or "tests" in f.relative_to(root).parts:return None
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
                        if owner:direct.add(owner)
                        for typ in cls.__mro__:
                            on=key(typ)
                            if on:ancestors.add(on)
                        if owner:seen.append(sym)
                records[item.nodeid]=dict(direct=sorted(direct),ancestors=sorted(ancestors),globals=sorted(seen))
    code=pytest.main(["-q","--collect-only","-o","addopts=","--disable-warnings",*json.loads(nodes.read_bytes())],plugins=[Observe()])
    target.write_text(json.dumps(dict(code=int(code),records=records),sort_keys=True)+"\n",encoding="utf8")
if __name__=="__main__":main()
