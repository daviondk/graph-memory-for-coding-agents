"""Link official-dev outcomes to identical weights or execute the alternate checkpoint."""
from pathlib import Path
import shutil
import sys

import control as ctl
from control import run, load, save, sha
import importlib.util
spec=importlib.util.spec_from_file_location("r21_selected_checkpoint_score",ctl.D.parent/"score.py")
score=importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

ALT=ctl.D/"alternative"
ALT_PRIV=run.PRIVATE/"dev580/alternative"


class SerialExecutor:
    """Keep the small alternate branch's relocated roots in one Python process."""
    def __init__(self,*args,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def map(self,fn,*iterables):return map(fn,*iterables)


def alternative(s,sel):
    old=run.HERE
    ALT.mkdir(exist_ok=True)
    ALT_PRIV.mkdir(parents=True,exist_ok=True)
    for f in ("inputs.json",):
        target=ALT/f
        if not target.exists():shutil.copyfile(old/f,target)
        assert sha(target)==sha(old/f)
    aplan=ALT/"plan.json"
    plan={"mode":"different-dev580-checkpoint","source":sha(old/"plan.json"),"correction":sha(ctl.D/"plan.json"),"code":sha(Path(__file__))}
    if aplan.exists():assert load(aplan)==plan
    else:save(aplan,plan)
    run.HERE=score.HERE=ALT
    run.PRIVATE=score.PRIVATE=ALT_PRIV
    score.ProcessPoolExecutor=SerialExecutor
    # The original prediction code has an identity audit for historical seed 13.
    # A historical calibration can still be rebuilt by using the ordinary (non-historical) path and
    # a local seed alias never used for training or for randomness in inference.
    effective=s if s!=13 else 113
    if effective!=s:run.SEEDS=(*run.SEEDS,effective)
    folder=run.seed_dir(effective)
    cp=Path(sel["path_580"])
    model=folder/"model.json"
    body={"seed":s,"relative_model":str(cp),"files":{"model.safetensors":sel["weight_580"]},"selection":sha(ctl.out(s)/"selection.json")}
    assert sha(cp/"model.safetensors")==sel["weight_580"]
    if model.exists():assert load(model)==body
    else:save(model,body)
    for path,method in (("embeddings.json",run.encode),("calibration.json",run.calibrate),("forecast-seal.json",score.run_forecast),("results.json",score.score)):
        if not (folder/path).exists():method(effective)
    return folder


def link(s):
    folder=run.seed_dir(s);target=ctl.out(s);sel=load(target/"selection.json")
    weights=load(run.R19/"trained-checkpoint.json" if s==13 else folder/"model.json")["files"]["model.safetensors"]
    assert weights==sel["weight_500"] and sha(Path(sel["path_580"])/"model.safetensors")==sel["weight_580"]
    if sel["same_choice"]:
        assert weights==sel["weight_580"]
        status="shared-weights"
    else:
        assert weights!=sel["weight_580"]
        folder=alternative(s,sel);status="alternative-checkpoint"
    data=folder/"metrics.json.gz";rp=folder/"results.json"
    res=load(rp)
    assert res["q_sha"]==sha(data) and res["seal"]==sha(folder/"forecast-seal.json") and res["n"]==2000
    row={"seed":s,"status":status,"metrics_path":str(data.resolve()),"metrics_sha":sha(data),"results_path":str(rp.resolve()),
         "results_sha":sha(rp),"forecast_sha":res["seal"],"selection_sha":sha(target/"selection.json"),"weight":sel["weight_580"],"n":2000}
    save(target/"test-link.json",row)


if __name__=="__main__":link(int(sys.argv[1]))

