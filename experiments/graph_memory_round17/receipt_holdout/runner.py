"""Run exactly the registered upstream unittest methods, recording only project function calls."""
import json
import os
import random
import sys
import time
import unittest
from pathlib import Path

def main():
    cwd=Path.cwd().resolve()
    sys.path.insert(0,str(cwd))
    jobs=json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    traces=sys.argv[2]=="trace"
    answers={}
    for case in jobs:
        name=case["name"]
        random.seed(177)
        suite=unittest.defaultTestLoader.loadTestsFromName(name)
        seen=set();files=set()
        def observe(frame,event,arg):
            if event!="call":return
            code=frame.f_code
            filename=code.co_filename.replace("\\","/")
            marker="/more_itertools/"
            if marker not in filename:return
            file="more_itertools/"+filename.split(marker)[-1]
            if not filename.lower().startswith(cwd.as_posix().lower()+"/"):return
            files.add(file)
            seen.add((file,code.co_qualname.split(".")[0]))
        result=unittest.TestResult()
        t=time.perf_counter()
        if traces:sys.setprofile(observe)
        try:suite.run(result)
        finally:sys.setprofile(None)
        errors=[{"test":str(t),"text":x} for t,x in result.errors]
        failures=[{"test":str(t),"text":x} for t,x in result.failures]
        skipped=[str(x) for x in result.skipped]
        outcome="infra" if any("_FailedTest" in r["test"] for r in errors) or result.testsRun!=1 else "fail" if errors or failures else "skip" if skipped else "pass"
        answers[name]={"outcome":outcome,"n":result.testsRun,"time":time.perf_counter()-t,"failures":failures,"errors":errors,"skips":skipped,"files":sorted(files),"calls":sorted(seen)}
    print(json.dumps(answers,ensure_ascii=True,sort_keys=True))
if __name__=="__main__":main()
