"""Serial GPU queue; independent sealed SWE-smith prompts only."""
import subprocess,sys,time
from common import *
path=ROOT.parent/'packets/live/reader_inputs.json'
out=ROOT.parent/'packets/live/capsule_calls'
for _ in range(1800):
    if (ROOT/'transfer/prediction_lock.json').exists():break
    time.sleep(2)
else:raise TimeoutError('transfer')
subprocess.run([sys.executable,'-Bu',str(ROOT/'run_packet_reader.py'),str(path),str(out),'--sha','02f070653e9c727cd783b36d42e23f5d9691a41441f13cad9b815e8b88fe076b'],check=True)
