"""Add a narrow Python stat/lstat observer around the previously frozen worker."""
import json
import os
from pathlib import Path
import runpy
import sys

def main():
    config=json.loads(Path(sys.argv[1]).read_bytes());out=Path(config["out"])
    resources={os.path.normcase(os.path.abspath(p)):p for p in config["resources"] if not p.endswith(".toml")}
    hits={p:set() for p in resources.values()};unknown=set()
    original={k:getattr(os,k) for k in ("stat","lstat")}
    def wrapper(name):
        method=original[name]
        def observed(path,*args,**kwargs):
            if resources and not isinstance(path,int):
                try:
                    src=os.fsdecode(path)
                    if kwargs.get("dir_fd") is not None and not os.path.isabs(src):unknown.add("relative_dir_fd")
                    else:
                        r=resources.get(os.path.normcase(os.path.abspath(src)))
                        if r:hits[r].add(name)
                except (TypeError,OSError,ValueError):unknown.add("unresolved_stat")
            return method(path,*args,**kwargs)
        return observed
    for n in original:setattr(os,n,wrapper(n))
    try:runpy.run_path(str(Path(__file__).resolve().parent.parent/"observe.py"),run_name="__main__")
    finally:
        for n,fn in original.items():setattr(os,n,fn)
    if out.is_file():
        data=json.loads(out.read_bytes());data["stat_reads"]={k:sorted(v) for k,v in hits.items()};data["stat_unknown"]=sorted(unknown)
        out.write_text(json.dumps(data,sort_keys=True),encoding="utf8")
if __name__=="__main__":main()
