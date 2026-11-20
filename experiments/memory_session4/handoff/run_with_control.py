import subprocess,time
from common import *
deadline=time.monotonic()+2700
while not (ROOT/'clean/reader_lock.json').exists():
    if time.monotonic()>deadline:raise TimeoutError('clean inference deadline')
    time.sleep(5)
with (ROOT/'shuffle/reader.log').open('w') as fp:
    subprocess.run(['python','-u',str(ROOT/'shuffle/reader.py')],check=True,stdout=fp,stderr=subprocess.STDOUT)
subprocess.run(['python',str(ROOT/'collect_labels.py')],check=True)
subprocess.run(['python',str(ROOT/'grade.py')],check=True)
subprocess.run(['python',str(ROOT/'control_grade.py')],check=True)
