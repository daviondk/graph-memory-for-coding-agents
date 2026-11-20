"""Run the project's native pytest tests and record within-frame target-code transitions."""
import gzip
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pytest

root=Path(sys.argv[1]).resolve()
name=sys.argv[2]
out=Path(sys.argv[3]).resolve()
out.mkdir(exist_ok=True,parents=True)
target=(root/"python_programs"/(name+".py")).resolve()
sys.path.insert(0,str(root))

class Observe:
    def __init__(self):
        self.records={}
        self.positions={}
        self.frames={}
        self.selected={}
    def trace(self,frame,event,arg):
        if event=="call":
            filename=frame.f_code.co_filename
            if filename not in self.selected:self.selected[filename]=Path(filename).resolve()==target
            if not self.selected[filename] or frame.f_code.co_name=="<module>":return None
            self.frames[id(frame)]=None
        elif event=="line":
            old=self.frames.get(id(frame))
            line=frame.f_lineno
            self.record["lines"].append(line)
            if old is not None:self.record["edges"].append([old,line])
            self.frames[id(frame)]=line
            if len(self.record["lines"])>15000:raise TimeoutError("per-test target trace budget")
        elif event=="return":
            old=self.frames.pop(id(frame),None)
            if old is not None:self.record["edges"].append([old,0])
        return self.trace

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self,item):
        self.record={"lines":[],"edges":[]}
        self.records[item.name]=self.record
        self.frames.clear()
        sys.settrace(self.trace)
        try:yield
        finally:sys.settrace(None)

    def pytest_runtest_logreport(self,report):
        if report.when=="call":
            rec=self.records.get(report.nodeid.split("::")[-1])
            if rec is not None:
                rec["status"]=report.outcome
                rec["failure"]=str(report.longrepr)[-650:] if report.failed else None

plugin=Observe()
rc=pytest.main([str(root/"python_testcases"/("test_"+name+".py")),"--runslow","--disable-warnings","-q","--tb=short","-o","addopts=","--junitxml="+str(out/"native.xml")],plugins=[plugin])
xml=out/"native.xml"
xml_outcomes={}
if xml.exists():
    for c in ET.parse(xml).iter("testcase"):
        lookup=[("failure","failed"),("error","error"),("skipped","skipped")]
        xml_outcomes[c.get("name")]=next((v for k,v in lookup if c.find(k) is not None),"passed")
raw=json.dumps({"rc":int(rc),"xml":xml_outcomes,"records":plugin.records},ensure_ascii=False,separators=(",",":")).encode()
(out/"trace.json.gz").write_bytes(gzip.compress(raw,mtime=0))
