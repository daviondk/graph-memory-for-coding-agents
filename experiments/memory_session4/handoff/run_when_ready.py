import subprocess,time
from common import ROOT
deadline=time.monotonic()+2700
while not (ROOT/'clean/reader_lock.json').exists():
    if time.monotonic()>deadline:raise TimeoutError('clean inference deadline')
    time.sleep(5)
subprocess.run(['python',str(ROOT/'collect_labels.py')],check=True)
subprocess.run(['python',str(ROOT/'grade.py')],check=True)
