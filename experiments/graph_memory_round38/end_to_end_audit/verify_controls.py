"""Independent post-run replay of released scoring code on measured Linux transcripts."""
import importlib.util,json,tempfile
from pathlib import Path
from grade_patch import ARGS,IMAGE,screen_diff
from inputs import D,R,V,row,save,sha
def main():
    spec=row()
    module_path=V/"scripts/vendor/eval.py"
    imp=importlib.util.spec_from_file_location("vendor_scoring",module_path)
    native=importlib.util.module_from_spec(imp);imp.loader.exec_module(native)
    tempfile.tempdir=str(R/"test-temp"); native.LOGS_DIR=R/"release-scorer"
    scored={}
    for name in ("linux-empty","linux-gold-final"):
        result=json.loads((D/"logs"/(name+".json")).read_text(encoding="utf8"))
        transcript=(D/"logs"/(name+".log")).read_text(encoding="utf8")
        def recorded(**kw):
            assert kw["image"]==IMAGE and kw["workdir"]=="/traitlets" and kw["test_cmds"]==[" ".join(["pytest",*ARGS])]
            # Only container transport is replaced with the already measured run. Native scorer recomputes its own result.
            return result["exit_code"],transcript
        native.run_in_container=recorded
        out=native.evaluate_instance(spec,IMAGE,None)
        assert result["passed_match"]==out["passed_match"]
        assert {i for i,s in result["parsed_statuses"].items() if s=="PASSED"}==set(out["passed_actual"])
        scored[name]={"expected":len(out["passed_expected"]),"observed_pass":len(out["passed_actual"]),"observed_fail":len(out["failed_actual"]),
                      "resolved":out["passed_match"],"log_sha":sha(D/"logs"/(name+".log"))}
    try:screen_diff((R/"test_patch.diff").read_bytes())
    except ValueError: test_diff_rejected=True
    else:raise AssertionError("test change accepted")
    save(D/"scorer-check.json",dict(scorer_sha=sha(module_path),arms=scored,test_diff_rejected=test_diff_rejected,
         scope="release evaluate_instance reads captured full Linux outputs for both controls; the container is run separately by grade_patch.py"))
    print(scored)
if __name__=="__main__":main()
