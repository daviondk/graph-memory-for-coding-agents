"""Assign official grades to the frozen universe, reusing a grade only after actual same-task byte comparison."""
from select_states import *
import shutil,sys
R12=VIBE/"grading";COUT=CP/"grading"
sys.path.insert(0,str(R12));from grade import run_eval,specs
PRIVATE=Path("D:/CodexResearch/x20-r14-evaluator-inputs")
def existing(task,h,b):
    for f in sorted((R12/"models"/task).glob("*/result.json")):
        info=get(f)
        if info["patch_sha"]!=h:continue
        actual=get(Path(info["official"]["seed_dir"])/"eval_input.json")[0]["patch"].encode()
        assert actual==b and info["instance"]==task
        return f,info["official"],f.parent/"native-report.json",f.parent/"unit.log"
    for f in sorted((COUT/task).glob("*/result.json")):
        info=get(f)
        if info.get("selected_sha")!=h:continue
        assert info["instance"]==task and raw_patch(info["selected_sha"])==b
        actual=get(Path(info["official_eval"]["seed_dir"])/"eval_input.json")[0]["patch"].encode()
        assert actual==b
        return f,info["official_eval"],f.parent/"native-report.json",f.parent/"unit.log"
    return None
def main():
    lock=get(D/"lock.json")
    for f,d in lock["inputs"].items():assert sha((D/f).read_bytes())==d
    assert lock["source_seal"]==sha((CP/"sealed.json").read_bytes())
    sources=get(D/"universe.json")
    for task,entries in sources.items():
        for h,ent in entries.items():
            out=D/"grades"/task/h;out.mkdir(exist_ok=True,parents=True);f=out/"grade.json";b=raw_patch(h)
            assert sha(b)==h and len(b)==ent["bytes"]
            if f.is_file():
                rec=get(f);assert rec["sha"]==h and rec["task"]==task
                continue
            prev=existing(task,h,b)
            if prev is not None:
                src,receipt,report,unit=prev;folder=src.parent
            else:
                wd=PRIVATE/task/h
                if wd.exists():raise RuntimeError("Uncompleted private result "+str(wd))
                wd.mkdir(exist_ok=False,parents=True)
                receipt=run_eval.evaluate_seed(run_eval.SeedRun(wd,task,b.decode()),specs,R12/"bridge.py",timeout=1800)
                report=wd/"eval_report.json";item=get(report)["items"][0] if report.is_file() else {}
                unit=wd/item.get("log_path","__no_unit__");src=None;folder=wd
            item=get(report)["items"][0] if report.is_file() else {}
            if report.is_file():shutil.copyfile(report,out/"native-report.json")
            if unit.is_file():shutil.copyfile(unit,out/"unit.log")
            for n in ("container.log","eval_stdout.log","eval_stderr.log"):
                if (folder/n).is_file():shutil.copyfile(folder/n,out/n)
            status="no_patch" if not b.strip() else "harness_error" if receipt.get("error") else "resolved" if receipt["resolved"] else "unresolved"
            result=dict(task=task,sha=h,size=len(b),status=status,resolved=receipt["resolved"],native=receipt,reused=bool(prev),
                source_result=str(src) if src else None,source_result_sha=sha(src.read_bytes()) if src else None,
                f2p=len(item.get("from_fail_to_pass",[])) if unit.is_file() else None,p2p_lost=len(item.get("failed_from_pass_to_pass",[])) if unit.is_file() else None,
                unit_exit=item.get("exit_code"),passed_match=item.get("passed_match"),unit_log=unit.is_file(),
                outputs={n.name:sha(n.read_bytes()) for n in out.iterdir() if n.is_file()})
            put(f,result);print(task,h[:12],status,"reused" if prev else "run",flush=True)
    manifest={}
    for t,entries in sources.items():
        for h in entries:
            f=D/"grades"/t/h/"grade.json";manifest[f.relative_to(D).as_posix()]=sha(f.read_bytes())
    put(D/"grading-lock.json",dict(complete=True,pairs=len(manifest),receipts=manifest,input_lock=sha((D/"lock.json").read_bytes()),runner=sha(Path(__file__).read_bytes())))
if __name__=="__main__":main()
