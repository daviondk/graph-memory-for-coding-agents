from pathlib import Path
import os,sys
for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS','RAYON_NUM_THREADS'):os.environ[k]='1'
os.environ['CUDA_VISIBLE_DEVICES']='-1'
D=Path(__file__).resolve().parent
W=D.parents[1]
R42=W/'graph_memory_round42/causal_ablation'
R43=W/'graph_memory_round43/relation_budget'
FIX=R43.parent/'fixed_trigger'
NATIVE=W/'graph_memory_round41/prefix_native'
sys.path.insert(0,str(R42))
from core42 import sha,save,read,SEEDS,firstfit,signed

def check_registration():
    receipt=read(D/'registration.json')
    assert receipt['protocol']==sha(D/'PROTOCOL_RU.md')
    for name,path in [('mid',R42),('bit',R43),('trigger',FIX),('native',NATIVE)]:
        assert sha(path/'manifest.json')==receipt[name]
