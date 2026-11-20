"""Read-only device sampling for the experiment-owned inference server."""
import datetime,json,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent
while not (ROOT/'stop_sampling').exists():
    t=time.time()
    try:
        out=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.free,utilization.gpu,temperature.gpu,driver_version','--format=csv,noheader'],timeout=10)
        status=out.decode().strip()
    except Exception as e:status=str(e)
    with (ROOT/'gpu_samples.jsonl').open('a') as file:file.write(json.dumps({'epoch':t,'status':status})+'\n')
    time.sleep(8)
