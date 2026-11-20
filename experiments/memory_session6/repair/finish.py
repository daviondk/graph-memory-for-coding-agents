import time
import subprocess
import sys
from common import *
for _ in range(360):
    if (ROOT/'prediction_lock.json').exists():break
    time.sleep(5)
else:raise TimeoutError('prediction lock')
for script,extra in [('grade.py',[]),('plus_grade.py',[]),('analyze.py',[]),('verify.py',['--record']),('report.py',[])]:
    print(stamp(),script,flush=True)
    subprocess.run([sys.executable,'-B','-u',str(ROOT/script),*extra],check=True,cwd=ROOT)
print(stamp(),'complete',flush=True)

