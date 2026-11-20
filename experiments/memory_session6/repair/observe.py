import subprocess
import time
from common import *
def main():
    out=ROOT/'runtime/gpu_samples.jsonl'
    while not (ROOT/'prediction_lock.json').exists():
        data=subprocess.check_output(['nvidia-smi','--query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw','--format=csv,noheader,nounits'],text=True).strip()
        with out.open('a',encoding='utf8') as f:f.write(canonical({'utc':stamp(),'nvidia_smi':data})+'\n')
        time.sleep(15)
if __name__=='__main__':main()

