import subprocess,time
from common import *
deadline=time.monotonic()+2700
for lock in ('clean/reader_lock.json','strict/input_lock.json'):
    while not (ROOT/lock).exists():
        if time.monotonic()>deadline:raise TimeoutError(lock)
        time.sleep(5)
for sub in ('shuffle','strict'):
    with (ROOT/sub/'reader.log').open('a') as fp:
        subprocess.run(['python','-u',str(ROOT/sub/'reader.py')],check=True,stdout=fp,stderr=subprocess.STDOUT)
subprocess.run(['python',str(ROOT/'collect_labels.py')],check=True)
for f in ('grade.py','control_grade.py','strict_grade.py'):
    subprocess.run(['python',str(ROOT/f)],check=True)
