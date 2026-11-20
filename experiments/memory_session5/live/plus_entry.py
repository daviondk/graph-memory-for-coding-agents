"""Pin NumPy BLAS threads for the 192 MiB Windows worker, then score frozen artifacts."""
import os,time
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from common import *
def main():
    for _ in range(2400):
        if (ROOT/'transfer/results.json').exists():break
        time.sleep(2)
    else:raise TimeoutError('author-test scoring')
    lock=read('evalplus_lock.json');assert all(digest((ROOT/f).read_bytes())==h for f,h in lock.items())
    import evalplus_score
    evalplus_score.main()
if __name__=='__main__':main()
