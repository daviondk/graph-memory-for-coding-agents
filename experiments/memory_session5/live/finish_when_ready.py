import subprocess,time,json
from common import *
def main():
    for _ in range(2400):
        if (ROOT/'transfer/prediction_lock.json').exists():break
        time.sleep(2)
    else:raise TimeoutError('prediction locks')
    for f,h in read('grade_lock.json').items():assert digest((ROOT/f).read_bytes())==h
    subprocess.run([sys.executable,'-B',str(ROOT/'grade.py')],check=True)
if __name__=='__main__':main()
