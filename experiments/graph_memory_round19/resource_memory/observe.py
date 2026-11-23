"""Collect Python-level file dependencies and actual pytest outcomes for one isolated repo."""
import json
import os
from pathlib import Path
import sys
import time

def main():
    cfg=json.loads(Path(sys.argv[1]).read_bytes())
    root=Path.cwd().resolve();out=Path(cfg["out"])
    def key(path):return os.path.normcase(os.path.abspath(path))
    resource={key(root/p):p for p in cfg["resources"]}
    methods={key(root/p):p for p in cfg["modules"]}
    pytest_reader=key(cfg["pytest_reader"])
    reads={p:set() for p in resource.values()};spawn=set();unknown=set()
    trace={p:{"calls":set(),"lines":set()} for p in methods.values()}
    enabled=True
    def hook(event,args):
        if not enabled:return
        if event in ("subprocess.Popen","os.system","os.posix_spawn","os.posix_spawnp","os.exec","os.fork","os.startfile","os.spawn"):
            spawn.add(event);return
        if event!="open" or not resource:return
        path=args[0]
        if isinstance(path,int):return
        try:r=resource.get(key(os.fsdecode(path)))
        except (ValueError,TypeError,OSError):unknown.add("unresolved audit path");return
        if r is None:return
        frame=sys._getframe(1)
        # Only this version-verified pytest function is allowed to project config sections.
        approved=False
        for _ in range(18):
            if frame is None:break
            name=frame.f_code.co_name
            if name=="load_config_dict_from_file" and key(frame.f_code.co_filename)==pytest_reader:
                approved=True;break
            # A call through another repo/plugin reader must not inherit pytest's label.
            frame=frame.f_back
        reads[r].add("pytest_config" if approved else "other")
    def watch(frame,event,arg):
        if event=="call":
            path=os.path.normcase(frame.f_code.co_filename)
            m=methods.get(path);r=resource.get(path)
            if r:reads[r].add("executed_helper")
            if not m:return None
            trace[m]["calls"].add(frame.f_code.co_qualname.replace(".<locals>.","."))
        elif event=="line":
            m=methods.get(os.path.normcase(frame.f_code.co_filename))
            if m:trace[m]["lines"].add(frame.f_lineno)
        return watch
    sys.path.insert(0,str(root));sys.addaudithook(hook);sys.settrace(watch)
    import pytest
    phases=[]
    class Capture:
        def pytest_runtest_logreport(self,report):phases.append((report.nodeid,report.when,report.outcome))
    try:rc=pytest.main(["-q","-o","addopts=","-p","no:cacheprovider",cfg["test"]],plugins=[Capture()])
    finally:sys.settrace(None);enabled=False
    origin=Path(sys.modules["loguru"].__file__).resolve()
    assert origin.is_relative_to(root)
    result={"pytest_rc":int(rc),"phases":phases,"trace":{p:{k:sorted(v) for k,v in m.items()} for p,m in trace.items()},
        "resource_reads":{p:sorted(v) for p,v in reads.items()},"subprocess_events":sorted(spawn),"unknown":sorted(unknown),"origin":str(origin)}
    out.write_text(json.dumps(result,sort_keys=True),encoding="utf8")
if __name__=="__main__":main()
